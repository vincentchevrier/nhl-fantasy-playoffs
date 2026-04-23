from datetime import datetime, date, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger


def save_snapshots(app):
    """Calculate each fantasy team's current total and save a dated snapshot."""
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
                    total += stat.wins + stat.shutouts

        snap = PointsSnapshot.query.filter_by(
            fantasy_team_id=team.id, date=today
        ).first()
        if snap:
            snap.points = total
        else:
            snap = PointsSnapshot(fantasy_team_id=team.id, date=today, points=total)
            db.session.add(snap)

    db.session.commit()
    print(f"[scheduler] Snapshots saved for {today}")


def refresh_playoff_stats(app):
    """Fetch current playoff stats and update DB. Runs nightly at 2am ET (7am UTC)."""
    from models import db, Player, Goalie, PlayoffSkaterStats, PlayoffGoalieStats, EliminatedTeam
    from nhlpy import NHLClient

    client = NHLClient()
    season = "20252026"

    with app.app_context():
        # --- Skater playoff stats ---
        skater_rows = []
        start = 0
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
            player = Player.query.get(pid)
            if not player:
                continue
            stat = PlayoffSkaterStats.query.filter_by(player_id=pid).first()
            if not stat:
                stat = PlayoffSkaterStats(player_id=pid)
                db.session.add(stat)
            stat.goals = s.get("goals", 0)
            stat.assists = s.get("assists", 0)
            stat.points = s.get("points", 0)
            stat.updated_at = datetime.utcnow()

        # --- Goalie playoff stats ---
        goalie_rows = []
        start = 0
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
            goalie = Goalie.query.get(gid)
            if not goalie:
                continue
            stat = PlayoffGoalieStats.query.filter_by(goalie_id=gid).first()
            if not stat:
                stat = PlayoffGoalieStats(goalie_id=gid)
                db.session.add(stat)
            stat.wins = g.get("wins", 0)
            stat.shutouts = g.get("shutouts", 0)
            stat.updated_at = datetime.utcnow()

        # --- Eliminated teams ---
        try:
            result = client.schedule.playoff_carousel(season=season)
            for rnd in result.get("rounds", []):
                for series in rnd.get("series", []):
                    top = series.get("topSeed", {})
                    bot = series.get("bottomSeed", {})
                    top_wins = top.get("wins", 0)
                    bot_wins = bot.get("wins", 0)
                    if top_wins == 4:
                        loser = bot.get("abbrev")
                    elif bot_wins == 4:
                        loser = top.get("abbrev")
                    else:
                        loser = None
                    if loser:
                        existing = EliminatedTeam.query.get(loser)
                        if not existing:
                            db.session.add(EliminatedTeam(team_abbr=loser))
        except Exception as e:
            print(f"[scheduler] Error fetching bracket: {e}")

        # Update last refresh timestamp
        from models import AppSetting
        setting = AppSetting.query.get("last_stats_refresh")
        now_iso = datetime.utcnow().isoformat()
        if setting:
            setting.value = now_iso
        else:
            db.session.add(AppSetting(key="last_stats_refresh", value=now_iso))

        db.session.commit()
        print(f"[scheduler] Playoff stats refreshed at {datetime.utcnow()}")
        save_snapshots(app)


def check_todays_schedule(app):
    """Daily job: fetch today's NHL schedule and store the game window in AppSetting."""
    from models import db, AppSetting
    from nhlpy import NHLClient

    with app.app_context():
        try:
            client = NHLClient()
            today_str = date.today().isoformat()
            data = client.schedule.daily_schedule(date=today_str)
            games = data.get("games", [])

            if not games:
                # No games today — clear the window
                _set_setting(db, AppSetting, "game_window_start", "")
                _set_setting(db, AppSetting, "game_window_end", "")
                db.session.commit()
                print(f"[scheduler] No games today ({today_str}), window cleared.")
                return

            # Window: earliest start → latest start + 3.5 hours
            start_times = []
            for g in games:
                t = g.get("startTimeUTC")
                if t:
                    start_times.append(t)

            if not start_times:
                return

            start_times.sort()
            window_start = start_times[0]
            # Parse latest start and add 3.5 hours for expected end
            latest_dt = datetime.fromisoformat(start_times[-1].replace("Z", "+00:00"))
            window_end = (latest_dt + timedelta(hours=3, minutes=30)).isoformat()

            _set_setting(db, AppSetting, "game_window_start", window_start)
            _set_setting(db, AppSetting, "game_window_end", window_end)
            db.session.commit()
            print(f"[scheduler] Game window set: {window_start} → {window_end}")

        except Exception as e:
            print(f"[scheduler] Error checking today's schedule: {e}")


def live_game_refresh(app):
    """Every-5-min job: refresh stats only if games are currently live."""
    from models import AppSetting
    from nhlpy import NHLClient

    with app.app_context():
        if not _in_game_window(AppSetting):
            return

        # Check whether any game is actually LIVE right now
        try:
            client = NHLClient()
            today_str = date.today().isoformat()
            data = client.schedule.daily_schedule(date=today_str)
            games = data.get("games", [])
            live = any(g.get("gameState") == "LIVE" for g in games)
        except Exception as e:
            print(f"[scheduler] live_game_refresh: schedule check failed: {e}")
            return

        if not live:
            return

        print("[scheduler] Live games detected — refreshing stats.")
        refresh_playoff_stats(app)


def _in_game_window(AppSetting):
    """Return True if current UTC time is within today's stored game window."""
    start_setting = AppSetting.query.get("game_window_start")
    end_setting = AppSetting.query.get("game_window_end")

    if not start_setting or not start_setting.value:
        return False
    if not end_setting or not end_setting.value:
        return False

    try:
        now = datetime.now(timezone.utc)
        window_start = datetime.fromisoformat(start_setting.value.replace("Z", "+00:00"))
        window_end = datetime.fromisoformat(end_setting.value.replace("Z", "+00:00"))
        # Make sure window is for today
        if window_start.date() != date.today():
            return False
        return window_start <= now <= window_end
    except Exception:
        return False


def should_page_refresh(AppSetting, cooldown_minutes=5):
    """Return True if we're in the game window and the cooldown has elapsed."""
    if not _in_game_window(AppSetting):
        return False

    last_setting = AppSetting.query.get("last_stats_refresh")
    if not last_setting or not last_setting.value:
        return True

    try:
        last_refresh = datetime.fromisoformat(last_setting.value)
        # Treat as UTC if naive
        if last_refresh.tzinfo is None:
            last_refresh = last_refresh.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - last_refresh
        return elapsed >= timedelta(minutes=cooldown_minutes)
    except Exception:
        return True


def _set_setting(db, AppSetting, key, value):
    setting = AppSetting.query.get(key)
    if setting:
        setting.value = value
    else:
        db.session.add(AppSetting(key=key, value=value))


def create_scheduler(app):
    scheduler = BackgroundScheduler()

    # Nightly stats refresh at 7am UTC (2am ET)
    scheduler.add_job(
        func=refresh_playoff_stats,
        args=[app],
        trigger=CronTrigger(hour=7, minute=0),
        id="nightly_refresh",
        replace_existing=True,
    )

    # Daily schedule check at 15:00 UTC (11am ET) — before most playoff games start
    scheduler.add_job(
        func=check_todays_schedule,
        args=[app],
        trigger=CronTrigger(hour=15, minute=0),
        id="daily_schedule_check",
        replace_existing=True,
    )

    # Every-5-min live check — only fires NHL API if within game window and games are LIVE
    scheduler.add_job(
        func=live_game_refresh,
        args=[app],
        trigger=IntervalTrigger(minutes=5),
        id="live_game_refresh",
        replace_existing=True,
    )

    scheduler.start()
    return scheduler
