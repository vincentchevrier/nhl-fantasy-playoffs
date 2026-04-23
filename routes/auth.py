import random
import string
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User

auth_bp = Blueprint("auth", __name__)


def _random_password(length=12):
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


def _send_signup_email(submitted_email, generated_password):
    try:
        import os
        from flask_mail import Mail, Message
        mail = Mail(current_app)
        notify_email = os.environ.get("SIGNUP_NOTIFY_EMAIL")
        if not notify_email:
            current_app.logger.warning("SIGNUP_NOTIFY_EMAIL not set — signup notification not sent.")
            return
        msg = Message(
            subject="New Fantasy Playoffs Signup",
            recipients=[notify_email],
            body=(
                f"New signup request:\n\n"
                f"Email: {submitted_email}\n"
                f"Generated password: {generated_password}\n\n"
                f"The user should be able to log in with these credentials."
            ),
        )
        mail.send(msg)
    except Exception as e:
        current_app.logger.warning(f"Failed to send signup email: {e}")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("standings.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash("Email is required.", "danger")
            return render_template("auth/signup.html")

        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
            return render_template("auth/signup.html")

        password = _random_password()
        user = User(email=email, must_change_pw=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        _send_signup_email(email, password)
        flash("Check your email for login details.", "success")
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
