from flask import Blueprint, render_template, abort
from flask_login import login_required
from models import FantasyTeam, FantasyPick, Player, Goalie, PlayoffSkaterStats, PlayoffGoalieStats, EliminatedTeam

teams_bp = Blueprint("teams", __name__)


def _fantasy_points_for_pick(pick, elim_set):
    """Return (points, is_eliminated) for a single pick."""
    if pick.player_id:
        player = pick.player
        is_elim = player.team in elim_set
        stat = player.playoff_stats
        if stat:
            pts = stat.goals * 2 + stat.assists
        else:
            pts = 0
        return pts, is_elim, player.name, player.team, player.position, "skater"
    elif pick.goalie_id:
        goalie = pick.goalie
        is_elim = goalie.team in elim_set
        stat = goalie.playoff_stats
        if stat:
            pts = stat.wins * 2 + stat.shutouts * 2
        else:
            pts = 0
        return pts, is_elim, goalie.name, goalie.team, "G", "goalie"
    return 0, False, "Unknown", "?", "?", "unknown"


def _team_total(fantasy_team, elim_set):
    total = 0
    for pick in fantasy_team.picks:
        pts, is_elim, *_ = _fantasy_points_for_pick(pick, elim_set)
        total += pts
    return total


@teams_bp.route("/teams")
@login_required
def teams_list():
    elim_set = {e.team_abbr for e in EliminatedTeam.query.all()}
    all_teams = FantasyTeam.query.all()
    ranked = sorted(all_teams, key=lambda t: _team_total(t, elim_set), reverse=True)
    teams_with_pts = [(t, _team_total(t, elim_set)) for t in ranked]
    return render_template("teams/list.html", teams=teams_with_pts, elim_set=elim_set)


@teams_bp.route("/teams/<int:team_id>")
@login_required
def team_detail(team_id):
    fantasy_team = FantasyTeam.query.get_or_404(team_id)
    elim_set = {e.team_abbr for e in EliminatedTeam.query.all()}

    roster = []
    total = 0
    for pick in sorted(fantasy_team.picks, key=lambda p: p.pool):
        pts, is_elim, name, team, position, ptype = _fantasy_points_for_pick(pick, elim_set)
        total += pts

        if pick.player_id:
            stat = pick.player.playoff_stats
            detail = {
                "goals": stat.goals if stat else 0,
                "assists": stat.assists if stat else 0,
                "points": stat.points if stat else 0,
            }
            player_id = pick.player_id
        else:
            stat = pick.goalie.playoff_stats if pick.goalie else None
            detail = {
                "wins": stat.wins if stat else 0,
                "shutouts": stat.shutouts if stat else 0,
            }
            player_id = pick.goalie_id

        roster.append({
            "pool": pick.pool,
            "name": name,
            "team": team,
            "position": position,
            "type": ptype,
            "player_id": player_id,
            "fantasy_points": pts,
            "is_eliminated": is_elim,
            "detail": detail,
        })

    return render_template("teams/detail.html", fantasy_team=fantasy_team, roster=roster, total=total)
