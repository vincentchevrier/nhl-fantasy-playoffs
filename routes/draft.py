from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required, current_user
from models import db, Player, Goalie, FantasyTeam, FantasyPick, AppSetting, EliminatedTeam

draft_bp = Blueprint("draft", __name__)

ALL_POOLS = (
    [f"F{i}" for i in range(1, 13)] +
    [f"D{i}" for i in range(1, 7)] +
    [f"G{i}" for i in range(1, 5)]
)


@draft_bp.route("/draft", methods=["GET"])
@login_required
def draft():
    playoffs_started = AppSetting.query.get("playoffs_started")
    playoffs_locked = playoffs_started and playoffs_started.value == "true"

    # Load all pooled players/goalies
    players = Player.query.filter(Player.pool.isnot(None)).order_by(Player.pool, Player.points.desc()).all()
    goalies = Goalie.query.filter(Goalie.pool.isnot(None)).order_by(Goalie.pool, (Goalie.wins + Goalie.shutouts).desc(), Goalie.wins.desc()).all()

    # Compute overall ranks within each position group
    forwards_sorted = sorted(
        [p for p in players if p.position in ("C", "L", "R")],
        key=lambda p: (-p.points, -p.goals)
    )
    defense_sorted = sorted(
        [p for p in players if p.position == "D"],
        key=lambda p: (-p.points, -p.goals)
    )
    player_ranks = {}
    for i, p in enumerate(forwards_sorted, 1):
        player_ranks[p.id] = i
    for i, p in enumerate(defense_sorted, 1):
        player_ranks[p.id] = i

    goalies_sorted = sorted(goalies, key=lambda g: (-(g.wins + g.shutouts), -g.wins))
    goalie_ranks = {g.id: i for i, g in enumerate(goalies_sorted, 1)}

    # Eliminated teams
    elim = {e.team_abbr for e in EliminatedTeam.query.all()}

    # Existing fantasy team + picks
    fantasy_team = FantasyTeam.query.filter_by(user_id=current_user.id).first()
    existing_picks = {}
    if fantasy_team:
        for pick in fantasy_team.picks:
            existing_picks[pick.pool] = pick.player_id or pick.goalie_id

    # When locked, resolve picks into a display list so the template needs no form
    locked_picks = []
    if playoffs_locked and fantasy_team:
        player_map = {p.id: p for p in players}
        goalie_map = {g.id: g for g in goalies}
        for pool in ALL_POOLS:
            pid = existing_picks.get(pool)
            if pid in player_map:
                p = player_map[pid]
                locked_picks.append({
                    "pool": pool, "name": p.name, "team": p.team,
                    "position": p.position, "player_id": p.id, "is_eliminated": p.team in elim,
                })
            elif pid in goalie_map:
                g = goalie_map[pid]
                locked_picks.append({
                    "pool": pool, "name": g.name, "team": g.team,
                    "position": "G", "player_id": g.id, "is_eliminated": g.team in elim,
                })

    return render_template(
        "draft.html",
        players=players,
        goalies=goalies,
        player_ranks=player_ranks,
        goalie_ranks=goalie_ranks,
        eliminated=elim,
        fantasy_team=fantasy_team,
        existing_picks=existing_picks,
        playoffs_locked=playoffs_locked,
        locked_picks=locked_picks,
        all_pools=ALL_POOLS,
    )


@draft_bp.route("/draft", methods=["POST"])
@login_required
def draft_submit():
    playoffs_started = AppSetting.query.get("playoffs_started")
    if playoffs_started and playoffs_started.value == "true":
        return jsonify({"success": False, "error": "Playoffs have started — draft is locked."}), 403

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Invalid request."}), 400

    team_name = (data.get("team_name") or "").strip()
    picks_data = data.get("picks", [])

    if not team_name:
        return jsonify({"success": False, "error": "Team name is required."}), 400

    # Validate all 22 pools covered
    submitted_pools = {p["pool"] for p in picks_data}
    missing = set(ALL_POOLS) - submitted_pools
    if missing:
        return jsonify({"success": False, "error": f"Missing picks for: {', '.join(sorted(missing))}"}), 400

    # Upsert FantasyTeam
    fantasy_team = FantasyTeam.query.filter_by(user_id=current_user.id).first()
    if fantasy_team:
        fantasy_team.name = team_name
        # Delete existing picks
        FantasyPick.query.filter_by(fantasy_team_id=fantasy_team.id).delete()
    else:
        fantasy_team = FantasyTeam(user_id=current_user.id, name=team_name)
        db.session.add(fantasy_team)
        db.session.flush()

    # Insert new picks
    for pick in picks_data:
        pool = pick["pool"]
        pid = pick.get("player_id")
        gid = pick.get("goalie_id")

        fp = FantasyPick(
            fantasy_team_id=fantasy_team.id,
            pool=pool,
            player_id=int(pid) if pid else None,
            goalie_id=int(gid) if gid else None,
        )
        db.session.add(fp)

    db.session.commit()
    return jsonify({"success": True, "team_id": fantasy_team.id})
