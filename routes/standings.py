import json
import threading
from flask import Blueprint, render_template, redirect, url_for, current_app
from flask_login import login_required, current_user
from models import Player, Goalie, PlayoffSkaterStats, PlayoffGoalieStats, EliminatedTeam, FantasyTeam, PointsSnapshot, AppSetting

standings_bp = Blueprint("standings", __name__)


def _maybe_trigger_refresh():
    """Spawn a background refresh if we're in the game window and cooldown has elapsed."""
    from scheduler import should_page_refresh, refresh_playoff_stats
    try:
        if should_page_refresh(AppSetting):
            app = current_app._get_current_object()
            t = threading.Thread(target=refresh_playoff_stats, args=[app], daemon=True)
            t.start()
    except Exception as e:
        current_app.logger.warning(f"Page-load refresh trigger failed: {e}")


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
                total += stat.wins + stat.shutouts
    return total


@standings_bp.route("/standings")
@login_required
def standings():
    _maybe_trigger_refresh()
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
        pts = (stat.wins + stat.shutouts) if stat else 0
        goalie_rows.append({
            "id": g.id,
            "name": g.name,
            "team": g.team,
            "pool": g.pool,
            "wins": stat.wins if stat else 0,
            "shutouts": stat.shutouts if stat else 0,
            "fantasy_points": pts,
            "is_eliminated": g.team in elim_set,
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

    bracket = {
        "west": {
            "r1": by_letter(r1, "E", "F", "G", "H"),
            "r2": r2[:2] if r2 else [None, None],
            "cf": r3[0] if r3 else None,
        },
        "east": {
            "r1": by_letter(r1, "A", "B", "C", "D"),
            "r2": r2[2:4] if len(r2) >= 4 else [None, None],
            "cf": r3[1] if len(r3) >= 2 else None,
        },
        "scf": r4[0] if r4 else None,
    }

    return render_template("bracket.html", bracket=bracket)


@standings_bp.route("/dashboard")
@login_required
def dashboard():
    _maybe_trigger_refresh()
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

    # Group by team
    from collections import defaultdict
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

    return render_template(
        "dashboard.html",
        user_team=user_team,
        user_rank=user_rank,
        user_total=user_total,
        total_teams=len(ranked),
        chart_traces=json.dumps(chart_traces),
    )
