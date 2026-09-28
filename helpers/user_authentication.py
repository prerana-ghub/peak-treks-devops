from functools import wraps

from flask import flash, g, redirect, request, session, url_for

from database import db
from models import User


def current_user():
    if session.get("user_id"):
        return db.session.get(User, session["user_id"])
    return None


def login_required(view):
    """Guarantees a real User row before the view runs."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            session.pop("user_id", None)
            flash("Sign in to continue.", "info")
            return redirect(url_for("user_authentication.signin", next=request.path))
        g.user = user
        return view(*args, **kwargs)
    return wrapper


def safe_next(raw):
    if raw and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return url_for("website_pages.index")
