"""
Page-load driven refresh logic.

On every authenticated page load, call maybe_refresh(app).
It runs in a background thread so the user never waits.

Rules:
  - Fetch today's schedule if last schedule check > 24h ago
  - Pull playoff stats if:
      * in game window AND last pull > 5 minutes ago, OR
      * last pull > 24 hours ago (daily catch-up)
"""

import threading
from datetime import datetime, timezone, timedelta, date


# ── Public entry point ────────────────────────────────────────────────────────

def maybe_refresh(app):
    """Spawn a background thread to check and refresh if needed."""
    t = threading.Thread(target=_run, args=[app], daemon=True)
    t.start()


# ── Core logic ────────────────────────────────────────────────────────────────

def _run(app):
    try:
        with app.app_context():
            from models import AppSetting
            _maybe_update_schedule(app, AppSetting)
            _maybe_refresh_stats(app, AppSetting)
    except Exception as e:
        app.logger.warning(f"[refresh] Background refresh error: {e}")


def _maybe_update_schedule(app, AppSetting):
    """Fetch today's game schedule if it hasn't been checked in the last 24h."""
    last = _get_setting(AppSetting, "last_schedule_check")
    if last and _age_hours(last) < 24:
        return
    _fetch_schedule(app, AppSetting)


def _maybe_refresh_stats(app, AppSetting):
    """Pull stats if in-game (5 min cooldown) or if it's been 24h since last pull."""
    last = _get_setting(AppSetting, "last_stats_refresh")
    age_minutes = _age_minutes(last) if last else float("inf")

    in_window = _in_game_window(AppSetting)

    if in_window and age_minutes >= 5:
        _refresh_stats(app, AppSetting)
    elif not in_window and age_minutes >= 60 * 24:
        _refresh_stats(app, AppSetting)


# ── Schedule fetch ────────────────────────────────────────────────────────────

def _fetch_schedule(app, AppSetting):
    from models import db
    try:
        from nhlpy import NHLClient
        client = NHLClient()
        today_str = date.today().isoformat()
        data = client.schedule.daily_schedule(date=today_str)
        games = data.get("games", [])

        if not games:
            _set_setting(db, AppSetting, "game_window_start", "")
            _set_setting(db, AppSetting, "game_window_end", "")
        else:
            from datetime import timedelta
            start_times = sorted(
                g["startTimeUTC"] for g in games if g.get("startTimeUTC")
            )
            window_start = start_times[0]
            latest_dt = datetime.fromisoformat(start_times[-1].replace("Z", "+00:00"))
            window_end = (latest_dt + timedelta(hours=3, minutes=30)).isoformat()
            _set_setting(db, AppSetting, "game_window_start", window_start)
            _set_setting(db, AppSetting, "game_window_end", window_end)

        _set_setting(db, AppSetting, "last_schedule_check",
                     datetime.now(timezone.utc).isoformat())
        db.session.commit()
        app.logger.info(f"[refresh] Schedule checked for {today_str}, {len(games)} game(s).")
    except Exception as e:
        app.logger.warning(f"[refresh] Schedule fetch failed: {e}")


# ── Stats refresh ─────────────────────────────────────────────────────────────

def _refresh_stats(app, AppSetting):
    from models import db, Player, Goalie, PlayoffSkaterStats, PlayoffGoalieStats, EliminatedTeam
    try:
        from nhlpy import NHLClient
        client = NHLClient()
        season = "20252026"

        # Skaters
        skater_rows, start = [], 0
        while True:
            batch = client.stats.skater_stats_summary(
                start_season=season, end_season=season,
                game_type_id=3, start=start, limit=100
            )
            if not batch:
                break
            skater_rows.extend(batch)
            if len(batch) < 100:
                break
            start += 100

        for s in skater_rows:
            pid = s["playerId"]
            if not Player.query.get(pid):
                continue
            stat = PlayoffSkaterStats.query.filter_by(player_id=pid).first()
            if not stat:
                stat = PlayoffSkaterStats(player_id=pid)
                db.session.add(stat)
            stat.goals = s.get("goals", 0)
            stat.assists = s.get("assists", 0)
            stat.points = s.get("points", 0)
            stat.updated_at = datetime.utcnow()

        # Goalies
        goalie_rows, start = [], 0
        while True:
            batch = client.stats.goalie_stats_summary(
                start_season=season, end_season=season,
                game_type_id=3, start=start, limit=100
            )
            if not batch:
                break
            goalie_rows.extend(batch)
            if len(batch) < 100:
                break
            start += 100

        for g in goalie_rows:
            gid = g["playerId"]
            if not Goalie.query.get(gid):
                continue
            stat = PlayoffGoalieStats.query.filter_by(goalie_id=gid).first()
            if not stat:
                stat = PlayoffGoalieStats(goalie_id=gid)
                db.session.add(stat)
            stat.wins = g.get("wins", 0)
            stat.shutouts = g.get("shutouts", 0)
            stat.updated_at = datetime.utcnow()

        # Eliminated teams
        try:
            result = client.schedule.playoff_carousel(season=season)
            for rnd in result.get("rounds", []):
                for series in rnd.get("series", []):
                    top = series.get("topSeed", {})
                    bot = series.get("bottomSeed", {})
                    loser = None
                    if top.get("wins") == 4:
                        loser = bot.get("abbrev")
                    elif bot.get("wins") == 4:
                        loser = top.get("abbrev")
                    if loser and not EliminatedTeam.query.get(loser):
                        db.session.add(EliminatedTeam(team_abbr=loser))
        except Exception as e:
            app.logger.warning(f"[refresh] Bracket fetch failed: {e}")

        now_iso = datetime.now(timezone.utc).isoformat()
        _set_setting(db, AppSetting, "last_stats_refresh", now_iso)
        db.session.commit()

        _save_snapshots(app)
        app.logger.info(f"[refresh] Stats refreshed at {now_iso}.")
    except Exception as e:
        app.logger.warning(f"[refresh] Stats refresh failed: {e}")


def _save_snapshots(app):
    from models import db, FantasyTeam, PointsSnapshot, EliminatedTeam
    today = date.today()
    elim_set = {e.team_abbr for e in EliminatedTeam.query.all()}
    for team in FantasyTeam.query.all():
        total = 0
        for pick in team.picks:
            if pick.player_id and pick.player:
                stat = pick.player.playoff_stats
                if stat:
                    total += stat.goals * 2 + stat.assists
            elif pick.goalie_id and pick.goalie:
                stat = pick.goalie.playoff_stats
                if stat:
                    total += stat.wins * 2 + stat.shutouts * 2
        snap = PointsSnapshot.query.filter_by(fantasy_team_id=team.id, date=today).first()
        if snap:
            snap.points = total
        else:
            db.session.add(PointsSnapshot(fantasy_team_id=team.id, date=today, points=total))
    db.session.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_setting(AppSetting, key):
    s = AppSetting.query.get(key)
    return s.value if s and s.value else None


def _set_setting(db, AppSetting, key, value):
    s = AppSetting.query.get(key)
    if s:
        s.value = value
    else:
        db.session.add(AppSetting(key=key, value=value))


def _age_minutes(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except Exception:
        return float("inf")


def _age_hours(iso_str):
    return _age_minutes(iso_str) / 60


def _in_game_window(AppSetting):
    start_s = _get_setting(AppSetting, "game_window_start")
    end_s = _get_setting(AppSetting, "game_window_end")
    if not start_s or not end_s:
        return False
    try:
        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(start_s.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_s.replace("Z", "+00:00"))
        if start.date() != date.today():
            return False
        return start <= now <= end
    except Exception:
        return False
