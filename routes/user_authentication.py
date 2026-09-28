from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import db
from models import User
from data.trek_catalog import PHOTOS
from helpers.shopping_cart import merge_cart_into_account
from helpers.user_authentication import safe_next
from helpers.user_notifications import notify

AUTH_PHOTO_SIGNIN = "/static/auth-signin.jpg"
AUTH_PHOTO_SIGNUP = "/static/auth-signup.jpg"

user_authentication = Blueprint("user_authentication", __name__)


@user_authentication.route("/signup", methods=["GET", "POST"])
def signup():
    form = {"name": "", "email": "", "phone": ""}
    next_url = safe_next(request.values.get("next"))

    if request.method == "POST":
        form = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "phone": request.form.get("phone", "").strip(),
        }
        password = request.form.get("password", "")

        if len(password) < 6:
            flash("Pick a password with at least 6 characters.", "error")
        elif User.query.filter_by(email=form["email"]).first():
            flash("An account already uses that email. Sign in instead.", "error")
            return redirect(url_for("user_authentication.signin", next=next_url))
        else:
            user = User(
                name=form["name"],
                email=form["email"],
                phone=form["phone"],
                password=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()

            session["user_id"] = user.id
            merge_cart_into_account(user)
            notify(
                user.id,
                "Welcome to PEAK",
                "Your account is ready. Pick a trail and a weekend.",
                "success",
                link="/treks"
            )
            flash(
                f"Account created. Welcome aboard, {user.name.split()[0]}.",
                "success"
            )
            return redirect(next_url if next_url != "/" else "/treks")

    return render_template(
        "auth.html",
        nav="auth",
        mode="signup",
        form=form,
        next_url=next_url,
        art=AUTH_PHOTO_SIGNUP,
        art_fallback=PHOTOS["kodachadri"]["remote"]
    )


@user_authentication.route("/signin", methods=["GET", "POST"])
def signin():
    form = {"name": "", "email": "", "phone": ""}
    next_url = safe_next(request.values.get("next"))

    if request.method == "POST":
        form["email"] = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=form["email"]).first()

        if not user or not check_password_hash(user.password, password):
            flash(
                "That email and password combination did not match an account.",
                "error"
            )
        else:
            session["user_id"] = user.id
            merge_cart_into_account(user)
            flash(
                f"Signed in. Good to see you, {user.name.split()[0]}.",
                "success"
            )
            return redirect(next_url)

    return render_template(
        "auth.html",
        nav="auth",
        mode="signin",
        form=form,
        next_url=next_url,
        art=AUTH_PHOTO_SIGNIN,
        art_fallback=PHOTOS["skandagiri"]["remote"]
    )


@user_authentication.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("cart_key", None)
    session.pop("pending_order_id", None)
    flash("Signed out. Your cart is saved to your account.", "info")
    return redirect("/")
