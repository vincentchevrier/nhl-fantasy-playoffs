from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("standings.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template("auth/signup.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("auth/signup.html")

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("auth/signup.html")

        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
            return render_template("auth/signup.html")

        user = User(email=email, must_change_pw=False, is_enabled=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Account created! You can log in once an admin enables your account.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/signup.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("standings.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html")

        if not user.is_enabled:
            flash("Your account is pending approval by an admin.", "warning")
            return render_template("auth/login.html")

        login_user(user)
        if user.must_change_pw:
            return redirect(url_for("auth.change_password"))

        next_page = request.args.get("next")
        return redirect(next_page or url_for("standings.dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        if len(new_password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("auth/change_password.html")

        if new_password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("auth/change_password.html")

        current_user.set_password(new_password)
        current_user.must_change_pw = False
        db.session.commit()
        flash("Password updated successfully.", "success")
        return redirect(url_for("standings.dashboard"))

    return render_template("auth/change_password.html")
