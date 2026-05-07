import os
from flask import Flask, redirect, url_for
from flask_login import LoginManager, current_user
from dotenv import load_dotenv
from models import db, User, AppSetting

load_dotenv()


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///fantasy_playoffs.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Flask-Mail config
    app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
    app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "True") == "True"
    app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "")
    app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER", "")

    db.init_app(app)

    from flask_mail import Mail
    Mail(app)

    login_manager = LoginManager(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from routes.auth import auth_bp
    from routes.draft import draft_bp
    from routes.teams import teams_bp
    from routes.standings import standings_bp
    from routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(draft_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(standings_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def inject_globals():
        pool_owner = os.environ.get("POOL_OWNER", "Collin's")
        return {"pool_owner": pool_owner}

    @app.before_request
    def trigger_refresh():
        from flask import request as req
        if req.endpoint == "static":
            return
        from flask_login import current_user
        if current_user.is_authenticated:
            from refresh import _maybe_update_schedule, _maybe_refresh_stats
            from models import AppSetting
            try:
                _maybe_update_schedule(app, AppSetting)
                _maybe_refresh_stats(app, AppSetting)
            except Exception as e:
                app.logger.warning(f"[refresh] Refresh error: {e}")

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("standings.dashboard"))
        return redirect(url_for("auth.login"))

    with app.app_context():
        db.create_all()
        _migrate_db()
        _seed_defaults()

    return app


def _migrate_db():
    """Add columns that may be missing from existing databases."""
    import sqlite3
    from flask import current_app
    db_path = os.path.join(current_app.instance_path, "fantasy_playoffs.db")
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "is_enabled" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_enabled INTEGER DEFAULT 0")
        # Enable the administrator account
        conn.execute("UPDATE users SET is_enabled = 1 WHERE email = 'administrator'")
        conn.commit()
    conn.close()


def _seed_defaults():
    """Seed admin user and default app settings if not present."""
    from models import User, AppSetting

    # Seed admin
    admin = User.query.filter_by(email="administrator").first()
    if not admin:
        admin = User(
            email="administrator",
            is_admin=True,
            is_enabled=True,
            must_change_pw=False,
        )
        admin.set_password(os.environ.get("ADMIN_PASSWORD", "CHANGEME"))
        db.session.add(admin)

    # Seed app settings
    defaults = {
        "playoffs_started": "false",
        "game_window_start": "",
        "game_window_end": "",
        "last_stats_refresh": "",
        "last_schedule_check": "",
        "today_games_cache": "",
        "today_games_cache_at": "",
        "today_games_date": "",
    }
    for key, value in defaults.items():
        if not AppSetting.query.get(key):
            db.session.add(AppSetting(key=key, value=value))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
