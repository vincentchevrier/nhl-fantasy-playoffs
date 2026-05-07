import json
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from models import Player, Goalie, PlayoffSkaterStats, PlayoffGoalieStats, EliminatedTeam, FantasyTeam, PointsSnapshot, AppSetting

standings_bp = Blueprint("standings", __name__)


def _team_total(fantasy_team, elim_set):
    total = 0
    for pick in fantasy_team.picks:
        if pick.player_id:
            stat = pick.player.playoff_stats if pick.player else None
            if stat:
                total += stat.goals * 2 + stat.assists
        elif pick.goalie_id:
            stat = pick.goalie.playoff_stats if pick.goalie else None
            if stat:
                total += stat.wins * 2 + stat.shutouts * 2
    return total


@standings_bp.route("/standings")
@login_required
def standings():
    elim_set = {e.team_abbr for e in EliminatedTeam.query.all()}

    # All pooled skaters with playoff stats
    skaters = (
        Player.query
        .filter(Player.pool.isnot(None))
        .outerjoin(PlayoffSkaterStats, Player.id == PlayoffSkaterStats.player_id)
        .all()
    )
    skater_rows = []
    for p in skaters:
        stat = p.playoff_stats
        pts = (stat.goals * 2 + stat.assists) if stat else 0
        skater_rows.append({
            "id": p.id,
            "name": p.name,
            "team": p.team,
            "position": p.position,
            "pool": p.pool,
            "goals": stat.goals if stat else 0,
            "assists": stat.assists if stat else 0,
            "fantasy_points": pts,
            "is_eliminated": p.team in elim_set,
            "reg_gp": p.gp,
            "reg_goals": p.goals,
            "reg_assists": p.assists,
            "reg_points": p.points,
        })
    skater_rows.sort(key=lambda x: x["fantasy_points"], reverse=True)

    goalie_rows = []
    goalies = (
        Goalie.query
        .filter(Goalie.pool.isnot(None))
        .outerjoin(PlayoffGoalieStats, Goalie.id == PlayoffGoalieStats.goalie_id)
        .all()
    )
    for g in goalies:
        stat = g.playoff_stats
        pts = (stat.wins * 2 + stat.shutouts * 2) if stat else 0
        goalie_rows.append({
            "id": g.id,
            "name": g.name,
            "team": g.team,
            "pool": g.pool,
            "wins": stat.wins if stat else 0,
            "shutouts": stat.shutouts if stat else 0,
            "fantasy_points": pts,
            "is_eliminated": g.team in elim_set,
            "reg_gp": g.gp,
            "reg_wins": g.wins,
            "reg_shutouts": g.shutouts,
            "reg_gaa": round(g.gaa, 2),
            "reg_sv_pct": round(g.sv_pct, 3),
        })
    goalie_rows.sort(key=lambda x: x["fantasy_points"], reverse=True)

    return render_template("standings.html", skaters=skater_rows, goalies=goalie_rows, elim_set=elim_set)


@standings_bp.route("/about")
@login_required
def about():
    return render_template("about.html")


@standings_bp.route("/bracket")
@login_required
def bracket():
    try:
        from nhlpy import NHLClient
        client = NHLClient()
        data = client.schedule.playoff_carousel(season="20252026")
        rounds = data.get("rounds", [])
    except Exception:
        rounds = []

    def get_round(rnum):
        for r in rounds:
            if r.get("roundNumber") == rnum:
                return r.get("series", [])
        return []

    r1 = get_round(1)
    r2 = get_round(2)
    r3 = get_round(3)
    r4 = get_round(4)

    def by_letter(series_list, *letters):
        m = {s["seriesLetter"]: s for s in series_list}
        return [m.get(l) for l in letters]

    def r1_teams(s):
        """Return the set of team abbrevs from an R1 series."""
        if not s:
            return set()
        return {s.get("topSeed", {}).get("abbrev"), s.get("bottomSeed", {}).get("abbrev")} - {None}

    def find_r2(r2_list, s1, s2):
        """Find the R2 series whose teams came from R1 series s1 and s2."""
        pool = r1_teams(s1) | r1_teams(s2)
        for s in r2_list:
            if not s:
                continue
            teams = {s.get("topSeed", {}).get("abbrev"), s.get("bottomSeed", {}).get("abbrev")} - {None}
            if teams & pool:
                return s
        return None

    west_r1 = by_letter(r1, "E", "F", "G", "H")
    east_r1 = by_letter(r1, "A", "B", "C", "D")

    bracket = {
        "west": {
            "r1": west_r1,
            "r2": [find_r2(r2, west_r1[0], west_r1[1]), find_r2(r2, west_r1[2], west_r1[3])],
            "cf": r3[0] if r3 else None,
        },
        "east": {
            "r1": east_r1,
            "r2": [find_r2(r2, east_r1[0], east_r1[1]), find_r2(r2, east_r1[2], east_r1[3])],
            "cf": r3[1] if len(r3) >= 2 else None,
        },
        "scf": r4[0] if r4 else None,
    }

    return render_template("bracket.html", bracket=bracket)


@standings_bp.route("/picks")
@login_required
def picks_summary():
    POOL_ORDER = (
        [f"F{i}" for i in range(1, 13)]
        + [f"D{i}" for i in range(1, 7)]
        + [f"G{i}" for i in range(1, 5)]
    )

    elim_set = {e.team_abbr for e in EliminatedTeam.query.all()}
    playoffs_setting = AppSetting.query.get("playoffs_started")
    show_pts = playoffs_setting and playoffs_setting.value == "true"

    teams = sorted(FantasyTeam.query.all(), key=lambda t: t.name.lower())

    # Build {team_id: {pool: {name, pts, team_abbr, is_elim}}}
    picks_map = {}
    # Also count how many teams picked each player_id/goalie_id per pool
    pick_counts = {}  # (pool, player_key) -> count

    for team in teams:
        picks_map[team.id] = {}
        for pick in team.picks:
            if pick.player_id and pick.player:
                p = pick.player
                stat = p.playoff_stats
                pts = (stat.goals * 2 + stat.assists) if stat else 0
                picks_map[team.id][pick.pool] = {
                    "name": p.name,
                    "pts": pts,
                    "team_abbr": p.team,
                    "is_elim": p.team in elim_set,
                    "key": f"p{pick.player_id}",
                }
                pick_counts[(pick.pool, f"p{pick.player_id}")] = pick_counts.get((pick.pool, f"p{pick.player_id}"), 0) + 1
            elif pick.goalie_id and pick.goalie:
                g = pick.goalie
                stat = g.playoff_stats
                pts = (stat.wins * 2 + stat.shutouts * 2) if stat else 0
                picks_map[team.id][pick.pool] = {
                    "name": g.name,
                    "pts": pts,
                    "team_abbr": g.team,
                    "is_elim": g.team in elim_set,
                    "key": f"g{pick.goalie_id}",
                }
                pick_counts[(pick.pool, f"g{pick.goalie_id}")] = pick_counts.get((pick.pool, f"g{pick.goalie_id}"), 0) + 1

    user_team = FantasyTeam.query.filter_by(user_id=current_user.id).first()
    user_team_id = user_team.id if user_team else None

    return render_template(
        "picks_summary.html",
        teams=teams,
        picks_map=picks_map,
        pick_counts=pick_counts,
        pool_order=POOL_ORDER,
        show_pts=show_pts,
        user_team_id=user_team_id,
    )


@standings_bp.route("/dashboard")
@login_required
def dashboard():
    from datetime import date, datetime, timezone, timedelta
    from collections import defaultdict

    elim_set = {e.team_abbr for e in EliminatedTeam.query.all()}
    all_teams = FantasyTeam.query.all()
    ranked = sorted(all_teams, key=lambda t: _team_total(t, elim_set), reverse=True)

    user_team = FantasyTeam.query.filter_by(user_id=current_user.id).first()
    user_rank = None
    user_total = 0
    if user_team:
        user_total = _team_total(user_team, elim_set)
        for i, t in enumerate(ranked, 1):
            if t.id == user_team.id:
                user_rank = i
                break

    # Build chart data: one trace per team, sorted by current points desc
    all_snapshots = (
        PointsSnapshot.query
        .order_by(PointsSnapshot.date)
        .all()
    )

    team_dates = defaultdict(list)
    team_points = defaultdict(list)
    for snap in all_snapshots:
        key = snap.fantasy_team_id
        team_dates[key].append(snap.date.isoformat())
        team_points[key].append(snap.points)

    chart_traces = []
    for team in ranked:
        dates = team_dates.get(team.id, [])
        points = team_points.get(team.id, [])
        if dates:
            chart_traces.append({
                "name": team.name,
                "x": dates,
                "y": points,
                "team_id": team.id,
            })

    # Today's games
    today_games = []
    try:
        from nhlpy import NHLClient
        client = NHLClient()
        result = client.game_center.daily_scores(date=date.today().isoformat())
        raw_games = result.get("games", [])

        # Build lookup: team_abbrev -> set of fantasy_team_ids with players on that NHL team
        from models import Player, Goalie, FantasyPick
        player_team = {}   # player_id -> team_abbrev
        goalie_team = {}   # goalie_id -> team_abbrev
        for p in Player.query.all():
            player_team[p.id] = p.team
        for g in Goalie.query.all():
            goalie_team[g.id] = g.team

        # Build per-game fantasy counts: game_id -> {fantasy_team_id: count}
        for g in raw_games:
            away_abbrev = g.get("awayTeam", {}).get("abbrev", "")
            home_abbrev = g.get("homeTeam", {}).get("abbrev", "")
            game_teams = {away_abbrev, home_abbrev}

            fantasy_counts = {}
            for ft in all_teams:
                count = 0
                for pick in ft.picks:
                    if pick.player_id and player_team.get(pick.player_id) in game_teams:
                        count += 1
                    elif pick.goalie_id and goalie_team.get(pick.goalie_id) in game_teams:
                        count += 1
                if count > 0:
                    fantasy_counts[ft.id] = {"name": ft.name, "count": count}

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

            # Period label
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
            in_intermission = clock.get("inIntermission", False)
            time_remaining = clock.get("timeRemaining", "")

            state = g.get("gameState", "FUT")
            # Normalize finished states
            if state in ("OFF", "FINAL"):
                state = "FINAL"

            today_games.append({
                "state": state,
                "start_time": start_time_display,
                "away": {
                    "abbrev": away_abbrev,
                    "logo": g.get("awayTeam", {}).get("logo", ""),
                    "score": g.get("awayTeam", {}).get("score"),
                },
                "home": {
                    "abbrev": home_abbrev,
                    "logo": g.get("homeTeam", {}).get("logo", ""),
                    "score": g.get("homeTeam", {}).get("score"),
                },
                "period_label": period_label,
                "in_intermission": in_intermission,
                "time_remaining": time_remaining,
                "fantasy_counts": fantasy_counts,
            })
    except Exception:
        today_games = []

    return render_template(
        "dashboard.html",
        user_team=user_team,
        user_rank=user_rank,
        user_total=user_total,
        total_teams=len(ranked),
        chart_traces=json.dumps(chart_traces),
        today_games=today_games,
        all_teams=ranked,
    )
