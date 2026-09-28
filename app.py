import os
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_wtf import CSRFProtect
from sqlalchemy import inspect as sa_inspect

load_dotenv()

from database import db
from trek_dates import pretty_date
from booking_billing import calculate_bill
from models import Trek, User
from helpers.user_authentication import current_user
from helpers.shopping_cart import get_cart_count
from helpers.user_notifications import get_unread_notif_count, get_recent_notifs
from data.trek_catalog import seed_treks

app = Flask(__name__)

app.secret_key = os.environ["SECRET_KEY"]

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "sqlite:///peak.db",
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "localhost")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 1025))
app.config["MAIL_SENDER"] = os.environ.get(
    "MAIL_SENDER",
    "bookings@peak-treks.test",
)
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")

if app.config["MAIL_USERNAME"] and "MAIL_SERVER" not in os.environ:
    app.config["MAIL_SERVER"] = "smtp.gmail.com"

if app.config["MAIL_USERNAME"] and "MAIL_PORT" not in os.environ:
    app.config["MAIL_PORT"] = 587

if app.config["MAIL_USERNAME"] and "MAIL_SENDER" not in os.environ:
    app.config["MAIL_SENDER"] = app.config["MAIL_USERNAME"]

app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "1") != "0"

db.init_app(app)
app.jinja_env.filters["pretty_date"] = pretty_date
csrf = CSRFProtect(app)

from routes.website_pages import website_pages
from routes.user_authentication import user_authentication
from routes.trek_booking import trek_booking

app.register_blueprint(website_pages)
app.register_blueprint(user_authentication)
app.register_blueprint(trek_booking)


@app.route("/healthz")
def healthz():
    return "ok", 200


@app.context_processor
def inject_globals():
    return {
        "current_user": current_user(),
        "cart_count": get_cart_count(),
        "unread_count": get_unread_notif_count(),
        "recent_notifs": get_recent_notifs(),
        "current_year": datetime.now().year,
    }


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


def prepare_database():
    inspector = sa_inspect(db.engine)

    if "trek" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("trek")}

        required_columns = {"slug", "itinerary", "state", "district"}

        if not required_columns.issubset(columns):
            if os.environ.get("RESET_DB") == "1":
                print("[DB] Old schema found. RESET_DB=1 is set, rebuilding tables.")
                db.drop_all()
                raise RuntimeError(
                    "Old database schema found. Refusing to drop tables. "
                    "Set RESET_DB=1 once if you really want to rebuild."
                )

    db.create_all()

    inspector = sa_inspect(db.engine)

    if "enquiry" in inspector.get_table_names():
        existing_columns = {
            column["name"]
            for column in inspector.get_columns("enquiry")
        }

        for name, ddl in [
            ("phone", "VARCHAR(30) DEFAULT ''"),
            ("emailed", "BOOLEAN DEFAULT 0"),
        ]:
            if name not in existing_columns:
                db.session.execute(
                    db.text(
                        f"ALTER TABLE enquiry ADD COLUMN {name} {ddl}"
                    )
                )
                print(f"[DB] Added enquiry.{name}.")

        db.session.commit()

    if Trek.query.count() == 0:
        seed_treks()


if __name__ == "__main__":
    with app.app_context():
        prepare_database()

    app.run(debug=True)
