from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, abort, request, flash
from flask_login import login_required, current_user
from models import db, User, FantasyTeam, FantasyPick, AppSetting, PlayoffSkaterStats, PlayoffGoalieStats, PointsSnapshot

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/admin")
@login_required
@admin_required
def admin():
    users = User.query.order_by(User.created_at).all()
    playoffs_started = AppSetting.query.get("playoffs_started")
    playoffs_value = playoffs_started.value if playoffs_started else "false"

    # Last refresh timestamp
    last_refresh = (
        db.session.query(db.func.max(PlayoffSkaterStats.updated_at)).scalar()
    )

    return render_template(
        "admin.html",
        users=users,
        playoffs_started=(playoffs_value == "true"),
        last_refresh=last_refresh,
    )


@admin_bp.route("/admin/refresh-stats", methods=["POST"])
@login_required
@admin_required
def refresh_stats():
    from flask import current_app
    from scheduler import refresh_playoff_stats, save_snapshots
    try:
        refresh_playoff_stats(current_app._get_current_object())
        flash("Stats refreshed successfully.", "success")
    except Exception as e:
        flash(f"Error refreshing stats: {e}", "danger")
    return redirect(url_for("admin.admin"))


@admin_bp.route("/admin/toggle-playoffs", methods=["POST"])
@login_required
@admin_required
def toggle_playoffs():
    setting = AppSetting.query.get("playoffs_started")
    if not setting:
        setting = AppSetting(key="playoffs_started", value="false")
        db.session.add(setting)

    if setting.value == "false":
        setting.value = "true"
        # Lock all existing fantasy teams
        FantasyTeam.query.update({"locked": True})
        flash("Playoffs started! All draft teams are now locked.", "success")
    else:
        setting.value = "false"
        flash("Playoffs marked as not started. Teams unlocked.", "info")
        FantasyTeam.query.update({"locked": False})

    db.session.commit()
    return redirect(url_for("admin.admin"))


@admin_bp.route("/admin/create-user", methods=["POST"])
@login_required
@admin_required
def create_user():
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "").strip()

    if not username or not password:
        flash("Username and password are required.", "danger")
        return redirect(url_for("admin.admin"))

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "danger")
        return redirect(url_for("admin.admin"))

    if User.query.filter_by(email=username).first():
        flash(f"A user with username '{username}' already exists.", "danger")
        return redirect(url_for("admin.admin"))

    user = User(email=username, must_change_pw=False, is_enabled=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f"User '{username}' created successfully.", "success")
    return redirect(url_for("admin.admin"))


@admin_bp.route("/admin/setup-pools", methods=["POST"])
@login_required
@admin_required
def setup_pools():
    from setup_pools import run_setup
    try:
        result = run_setup()
        flash(
            f"Pools seeded: {result['forwards']} forwards, {result['defensemen']} defensemen, "
            f"{result['goalies']} goalies.",
            "success",
        )
    except Exception as e:
        flash(f"Setup failed: {e}", "danger")
    return redirect(url_for("admin.admin"))


@admin_bp.route("/admin/toggle-user/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.email == "administrator":
        flash("Cannot disable the administrator account.", "danger")
        return redirect(url_for("admin.admin"))
    user.is_enabled = not user.is_enabled
    db.session.commit()
    status = "enabled" if user.is_enabled else "disabled"
    flash(f"'{user.email}' {status}.", "success")
    return redirect(url_for("admin.admin"))


@admin_bp.route("/admin/rename-user/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def rename_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.email == "administrator":
        flash("Cannot rename the administrator account.", "danger")
        return redirect(url_for("admin.admin"))
    new_username = request.form.get("username", "").strip().lower()
    if not new_username:
        flash("Username cannot be empty.", "danger")
        return redirect(url_for("admin.admin"))
    if User.query.filter(User.email == new_username, User.id != user_id).first():
        flash(f"Username '{new_username}' is already taken.", "danger")
        return redirect(url_for("admin.admin"))
    old = user.email
    user.email = new_username
    db.session.commit()
    flash(f"Username changed from '{old}' to '{new_username}'.", "success")
    return redirect(url_for("admin.admin"))


@admin_bp.route("/admin/delete-user/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.email == "administrator":
        flash("Cannot delete the administrator account.", "danger")
        return redirect(url_for("admin.admin"))

    # Cascade: picks → snapshots → teams → user
    for team in user.fantasy_teams:
        FantasyPick.query.filter_by(fantasy_team_id=team.id).delete()
        PointsSnapshot.query.filter_by(fantasy_team_id=team.id).delete()
    FantasyTeam.query.filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f"User '{user.email}' deleted.", "success")
    return redirect(url_for("admin.admin"))
