from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    must_change_pw = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_enabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    fantasy_teams = db.relationship("FantasyTeam", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Player(db.Model):
    __tablename__ = "players"
    id = db.Column(db.Integer, primary_key=True)  # NHL player_id
    name = db.Column(db.String(255), nullable=False)
    team = db.Column(db.String(10), nullable=False)
    position = db.Column(db.String(5), nullable=False)
    pool = db.Column(db.String(5), nullable=True)  # F1-F12, D1-D6, or NULL
    gp = db.Column(db.Integer, default=0)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    points = db.Column(db.Integer, default=0)

    picks = db.relationship("FantasyPick", backref="player", lazy=True)
    playoff_stats = db.relationship("PlayoffSkaterStats", backref="player", uselist=False, lazy=True)


class Goalie(db.Model):
    __tablename__ = "goalies"
    id = db.Column(db.Integer, primary_key=True)  # NHL player_id
    name = db.Column(db.String(255), nullable=False)
    team = db.Column(db.String(10), nullable=False)
    pool = db.Column(db.String(5), nullable=True)  # G1-G4 or NULL
    gp = db.Column(db.Integer, default=0)
    wins = db.Column(db.Integer, default=0)
    gaa = db.Column(db.Float, default=0.0)
    sv_pct = db.Column(db.Float, default=0.0)
    shutouts = db.Column(db.Integer, default=0)

    picks = db.relationship("FantasyPick", backref="goalie", lazy=True)
    playoff_stats = db.relationship("PlayoffGoalieStats", backref="goalie", uselist=False, lazy=True)


class FantasyTeam(db.Model):
    __tablename__ = "fantasy_teams"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    locked = db.Column(db.Boolean, default=False)

    picks = db.relationship("FantasyPick", backref="fantasy_team", lazy=True, cascade="all, delete-orphan")


class FantasyPick(db.Model):
    __tablename__ = "fantasy_picks"
    id = db.Column(db.Integer, primary_key=True)
    fantasy_team_id = db.Column(db.Integer, db.ForeignKey("fantasy_teams.id"), nullable=False)
    pool = db.Column(db.String(5), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=True)
    goalie_id = db.Column(db.Integer, db.ForeignKey("goalies.id"), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("fantasy_team_id", "pool", name="uq_team_pool"),
    )


class PlayoffSkaterStats(db.Model):
    __tablename__ = "playoff_skater_stats"
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), unique=True, nullable=False)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    points = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class PlayoffGoalieStats(db.Model):
    __tablename__ = "playoff_goalie_stats"
    id = db.Column(db.Integer, primary_key=True)
    goalie_id = db.Column(db.Integer, db.ForeignKey("goalies.id"), unique=True, nullable=False)
    wins = db.Column(db.Integer, default=0)
    shutouts = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class EliminatedTeam(db.Model):
    __tablename__ = "eliminated_teams"
    team_abbr = db.Column(db.String(10), primary_key=True)
    eliminated_at = db.Column(db.DateTime, default=datetime.utcnow)


class PointsSnapshot(db.Model):
    """Daily snapshot of each fantasy team's total points."""
    __tablename__ = "points_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    fantasy_team_id = db.Column(db.Integer, db.ForeignKey("fantasy_teams.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    points = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.UniqueConstraint("fantasy_team_id", "date", name="uq_team_date"),
    )

    fantasy_team = db.relationship("FantasyTeam", backref="snapshots")


class AppSetting(db.Model):
    __tablename__ = "app_settings"
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.String(500), nullable=False)
