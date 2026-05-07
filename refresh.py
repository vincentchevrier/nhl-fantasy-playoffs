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


def backfill_snapshots(app):
    """Backfill missing PointsSnapshot rows using per-game playoff logs.

    For each date from the first playoff game to yesterday, calculates each
    team's accurate cumulative fantasy points and inserts any missing snapshot.
    Already-calculated dates are skipped.
    """
    from models import db, FantasyTeam, FantasyPick, PointsSnapshot
    try:
        from nhlpy import NHLClient
        client = NHLClient()
        season = "20252026"

        # Collect all drafted player/goalie IDs
        all_picks = FantasyPick.query.all()
        player_ids = {p.player_id for p in all_picks if p.player_id}
        goalie_ids = {p.goalie_id for p in all_picks if p.goalie_id}

        # Fetch game logs — build {id: sorted list of (date_str, cumulative_stat)}
        # For skaters: cumulative (goals, assists) after each game date
        # For goalies: cumulative (wins, shutouts) after each game date
        player_logs = {}   # player_id -> [(date_str, cum_goals, cum_assists), ...]
        goalie_logs = {}   # goalie_id -> [(date_str, cum_wins, cum_shutouts), ...]

        for pid in player_ids:
            try:
                games = client.stats.player_game_log(pid, season_id=season, game_type=3)
                games = sorted(games, key=lambda g: g.get("gameDate", ""))
                cum_g, cum_a = 0, 0
                entries = []
                for game in games:
                    d = game.get("gameDate")
                    if not d:
                        continue
                    cum_g += game.get("goals", 0)
                    cum_a += game.get("assists", 0)
                    entries.append((d, cum_g, cum_a))
                player_logs[pid] = entries
            except Exception:
                player_logs[pid] = []

        for gid in goalie_ids:
            try:
                games = client.stats.player_game_log(gid, season_id=season, game_type=3)
                games = sorted(games, key=lambda g: g.get("gameDate", ""))
                cum_w, cum_so = 0, 0
                entries = []
                for game in games:
                    d = game.get("gameDate")
                    if not d:
                        continue
                    cum_w += 1 if game.get("decision") == "W" else 0
                    cum_so += game.get("shutouts", 0)
                    entries.append((d, cum_w, cum_so))
                goalie_logs[gid] = entries
            except Exception:
                goalie_logs[gid] = []

        # Find the date range: first game date → yesterday
        all_dates = [e[0] for logs in player_logs.values() for e in logs] + \
                    [e[0] for logs in goalie_logs.values() for e in logs]
        if not all_dates:
            app.logger.info("[backfill] No playoff game log data found.")
            return

        first_date = date.fromisoformat(min(all_dates))
        yesterday = date.today() - timedelta(days=1)

        def stats_as_of(entries, target_date_str):
            """Return the last cumulative entry on or before target_date_str."""
            result = entries[0][1:] if entries else None
            result = None
            for entry in entries:
                if entry[0] <= target_date_str:
                    result = entry[1:]
                else:
                    break
            return result

        # Find existing snapshot dates per team to skip already-calculated ones
        all_teams = FantasyTeam.query.all()
        existing = {}  # team_id -> set of date objects
        for snap in PointsSnapshot.query.all():
            existing.setdefault(snap.fantasy_team_id, set()).add(snap.date)

        inserted = 0
        cur = first_date
        while cur <= yesterday:
            cur_str = cur.isoformat()
            for team in all_teams:
                team_start = team.submitted_at.date() if team.submitted_at else first_date
                if cur < team_start:
                    continue
                if cur in existing.get(team.id, set()):
                    continue

                total = 0
                for pick in team.picks:
                    if pick.player_id:
                        entry = stats_as_of(player_logs.get(pick.player_id, []), cur_str)
                        if entry:
                            total += entry[0] * 2 + entry[1]  # goals*2 + assists
                    elif pick.goalie_id:
                        entry = stats_as_of(goalie_logs.get(pick.goalie_id, []), cur_str)
                        if entry:
                            total += entry[0] * 2 + entry[1] * 2  # wins*2 + shutouts*2

                db.session.add(PointsSnapshot(fantasy_team_id=team.id, date=cur, points=total))
                inserted += 1

            cur += timedelta(days=1)

        db.session.commit()
        app.logger.info(f"[backfill] Inserted {inserted} missing snapshots.")
    except Exception as e:
        app.logger.warning(f"[backfill] Failed: {e}")


# ── Today's games cache ───────────────────────────────────────────────────────

def refresh_today_games(app):
    """Fetch today's games from NHL API and cache in AppSetting as JSON.

    Skater points come from the goals array in daily_scores (no extra call).
    Goalie points come from boxscore (one call per started game).
    """
    import json
    from models import db, AppSetting

    try:
        from nhlpy import NHLClient
        client = NHLClient()
        result = client.game_center.daily_scores()
        raw_games = result.get("games", [])
        nhl_date = result.get("currentDate", "")

        games_out = []
        for g in raw_games:
            away = g.get("awayTeam", {})
            home = g.get("homeTeam", {})
            game_state = g.get("gameState", "FUT")

            # Skater points from goals array
            skater_game_pts = {}
            for goal in g.get("goals", []):
                sid = goal.get("playerId")
                if sid:
                    skater_game_pts[sid] = skater_game_pts.get(sid, 0) + 2
                for assist in goal.get("assists", []):
                    aid = assist.get("playerId")
                    if aid:
                        skater_game_pts[aid] = skater_game_pts.get(aid, 0) + 1

            # Goalie points from boxscore (only when game has started)
            goalie_game_pts = {}
            if game_state not in ("FUT", "PRE"):
                try:
                    bs = client.game_center.boxscore(game_id=str(g["id"]))
                    pg = bs.get("playerByGameStats", {})
                    for side in ("awayTeam", "homeTeam"):
                        for gl in pg.get(side, {}).get("goalies", []):
                            gid = gl.get("playerId")
                            if gl.get("decision") == "W":
                                pts = 2
                                if gl.get("goalsAgainst", 1) == 0:
                                    pts += 2
                                goalie_game_pts[gid] = pts
                except Exception:
                    pass

            # Format start time in ET
            start_time_display = ""
            start_utc = g.get("startTimeUTC", "")
            if start_utc:
                try:
                    dt = datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
                    et_offset = g.get("easternUTCOffset", "-04:00")
                    hours = int(et_offset.split(":")[0])
                    dt_et = dt + timedelta(hours=hours)
                    start_time_display = dt_et.strftime("%-I:%M %p ET")
                except Exception:
                    start_time_display = start_utc

            period_desc = g.get("periodDescriptor", {})
            period_num = period_desc.get("number", 0)
            period_type = period_desc.get("periodType", "REG")
            if period_type == "OT":
                period_label = "OT"
            elif period_type == "SO":
                period_label = "SO"
            else:
                period_label = {1: "1st", 2: "2nd", 3: "3rd"}.get(period_num, f"P{period_num}")

            clock = g.get("clock") or {}
            normalized_state = "FINAL" if game_state in ("OFF", "FINAL") else game_state

            games_out.append({
                "state": normalized_state,
                "start_time": start_time_display,
                "away": {"abbrev": away.get("abbrev", ""), "logo": away.get("logo", ""), "score": away.get("score")},
                "home": {"abbrev": home.get("abbrev", ""), "logo": home.get("logo", ""), "score": home.get("score")},
                "period_label": period_label,
                "in_intermission": clock.get("inIntermission", False),
                "time_remaining": clock.get("timeRemaining", ""),
                "skater_game_pts": skater_game_pts,
                "goalie_game_pts": goalie_game_pts,
            })

        _set_setting(db, AppSetting, "today_games_cache", json.dumps(games_out))
        _set_setting(db, AppSetting, "today_games_date", nhl_date)
        _set_setting(db, AppSetting, "today_games_cache_at", datetime.now(timezone.utc).isoformat())
        db.session.commit()
        app.logger.info(f"[refresh] Today's games cached: {len(games_out)} game(s) for {nhl_date}.")
    except Exception as e:
        app.logger.warning(f"[refresh] Today's games cache failed: {e}")


def maybe_refresh_today_games(app, AppSetting):
    """Refresh today's games cache if stale.

    TTL is 2 minutes when any game is live, 15 minutes otherwise.
    """
    import json
    cache_at = _get_setting(AppSetting, "today_games_cache_at")
    age = _age_minutes(cache_at) if cache_at else float("inf")

    # Determine TTL based on whether any game is currently live
    cached = _get_setting(AppSetting, "today_games_cache")
    has_live = False
    if cached:
        try:
            games = json.loads(cached)
            has_live = any(g.get("state") in ("LIVE", "CRIT", "PRE") for g in games)
        except Exception:
            pass

    ttl = 2 if has_live else 15
    if age >= ttl:
        refresh_today_games(app)


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
