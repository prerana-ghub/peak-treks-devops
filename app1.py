import base64
import io
import json
import os
import smtplib
import uuid
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

import qrcode
from urllib.parse import quote
from dotenv import load_dotenv
from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)
from flask_sqlalchemy import SQLAlchemy
from jinja2 import DictLoader
from sqlalchemy import inspect as sa_inspect
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    """Current wall-clock time in Bengaluru, as a naive datetime so it
    compares and formats the same way the rest of the app already expects."""
    return datetime.now(IST).replace(tzinfo=None)


def today_ist():
    return now_ist().date()


app = Flask(__name__, static_folder=".", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "peak-secret-key")

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///peak.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ---------------- email config ----------------
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "localhost")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 1025))
app.config["MAIL_SENDER"] = os.environ.get("MAIL_SENDER", "bookings@peak-treks.test")
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")

if app.config["MAIL_USERNAME"] and "MAIL_SERVER" not in os.environ:
    app.config["MAIL_SERVER"] = "smtp.gmail.com"
if app.config["MAIL_USERNAME"] and "MAIL_PORT" not in os.environ:
    app.config["MAIL_PORT"] = 587
if app.config["MAIL_USERNAME"] and "MAIL_SENDER" not in os.environ:
    app.config["MAIL_SENDER"] = app.config["MAIL_USERNAME"]
app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "1") != "0"

UPI_PAYEE_VPA = "bookings@peak"
UPI_PAYEE_NAME = "PEAK Treks"

AUTH_PHOTO_SIGNIN = "/signin.jpg"
AUTH_PHOTO_SIGNUP = "/signup.jpg"
CTA_PHOTO = "/booktrek.jpg"
ERROR_PHOTO = "/error.jpg"

GST_RATE = 0.05
BOOKING_FEE = 49
MIN_PEOPLE = 1
MAX_PEOPLE = 20

db = SQLAlchemy(app)


# ================================================================
# MODELS
# ================================================================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=now_ist)

    def initials(self):
        parts = [p for p in self.name.split() if p]
        if not parts:
            return "P"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class Trek(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)

    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(150), nullable=False)
    district = db.Column(db.String(80), nullable=False, default="")
    state = db.Column(db.String(80), nullable=False, default="Karnataka")
    region = db.Column(db.String(80), nullable=False, default="Western Ghats")
    tagline = db.Column(db.String(200), nullable=False, default="")

    description = db.Column(db.Text, nullable=False)
    long_description = db.Column(db.Text, nullable=False, default="")

    price = db.Column(db.Integer, nullable=False)

    difficulty = db.Column(db.String(50), nullable=False)
    difficulty_band = db.Column(db.String(20), nullable=False, default="Moderate")
    duration = db.Column(db.String(50), nullable=False)
    distance = db.Column(db.String(50), nullable=False)
    altitude = db.Column(db.String(50), nullable=False)
    group_size = db.Column(db.String(50), nullable=False, default="6 – 15 trekkers")

    starting_point = db.Column(db.String(150), nullable=False)
    ending_point = db.Column(db.String(150), nullable=False)
    best_season = db.Column(db.String(150), nullable=False)

    how_to_reach = db.Column(db.Text, nullable=False)
    highlights = db.Column(db.Text, nullable=False)
    things_to_carry = db.Column(db.Text, nullable=False)
    inclusions = db.Column(db.Text, nullable=False, default="")
    exclusions = db.Column(db.Text, nullable=False, default="")
    safety_info = db.Column(db.Text, nullable=False)
    permit_info = db.Column(db.Text, nullable=False)

    itinerary = db.Column(db.Text, nullable=False, default="[]")   # JSON
    faqs = db.Column(db.Text, nullable=False, default="[]")        # JSON
    gallery = db.Column(db.Text, nullable=False, default="[]")     # JSON

    image_url = db.Column(db.String(255), nullable=False)
    fallback_image = db.Column(db.String(255), nullable=False, default="")

    rating = db.Column(db.Float, nullable=False, default=4.8)
    reviews_count = db.Column(db.Integer, nullable=False, default=0)
    featured = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    def highlight_list(self):
        return [x.strip() for x in self.highlights.split(";") if x.strip()]

    def carry_list(self):
        return [x.strip() for x in self.things_to_carry.split(";") if x.strip()]

    def inclusion_list(self):
        return [x.strip() for x in self.inclusions.split(";") if x.strip()]

    def exclusion_list(self):
        return [x.strip() for x in self.exclusions.split(";") if x.strip()]

    def itinerary_list(self):
        try:
            return json.loads(self.itinerary or "[]")
        except ValueError:
            return []

    def faq_list(self):
        try:
            return json.loads(self.faqs or "[]")
        except ValueError:
            return []

    def gallery_list(self):
        try:
            return json.loads(self.gallery or "[]")
        except ValueError:
            return []


class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cart_key = db.Column(db.String(40), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    trek_id = db.Column(db.Integer, db.ForeignKey("trek.id"), nullable=False)
    trek_slug = db.Column(db.String(80), nullable=False, default="")
    trek_name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(150), nullable=False)
    image_url = db.Column(db.String(255), nullable=True)

    trek_date = db.Column(db.String(20), nullable=False)
    people = db.Column(db.Integer, nullable=False, default=1)
    price = db.Column(db.Integer, nullable=False)

    added_at = db.Column(db.DateTime, default=now_ist)

    def subtotal(self):
        return self.price * self.people


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_ref = db.Column(db.String(40), unique=True, nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)

    subtotal = db.Column(db.Integer, nullable=False, default=0)
    gst = db.Column(db.Integer, nullable=False, default=0)
    booking_fee = db.Column(db.Integer, nullable=False, default=0)
    total = db.Column(db.Integer, nullable=False)

    status = db.Column(db.String(30), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, default=now_ist)

    payments = db.relationship("Payment", backref="order", lazy=True)

    def items(self):
        return OrderItem.query.filter_by(order_id=self.id).all()

    def latest_payment(self):
        return (Payment.query.filter_by(order_id=self.id)
                .order_by(Payment.id.desc()).first())

    def display_ref(self):
        """The reference as shown in the cart UI.

        Rows created before the reference format changed still carry the old
        PEAK-XXXXXXXX value. This renders those in the current
        PEAK-<TREK>-<DATE>-<SUFFIX> style so the cart never shows two
        competing identifiers. Nothing is written back: order_ref, the row id
        and the reference printed on already-sent receipts are untouched.
        """
        raw = self.order_ref or ""
        parts = [p for p in raw.split("-") if p]
        if len(parts) >= 4:
            return raw

        items = self.items()
        if not items:
            return raw

        slug = items[0].trek_slug or ""
        code = TREK_CODES.get(slug) or (slug or "TRK")[:3].upper()
        distinct = {i.trek_slug for i in items if i.trek_slug}
        if len(distinct) > 1:
            code = f"{code}+{len(distinct) - 1}"
        try:
            date_part = datetime.strptime(items[0].trek_date, "%Y-%m-%d").strftime("%d%b").upper()
        except (ValueError, TypeError):
            date_part = ""
        suffix = (parts[-1] if len(parts) > 1 else f"{self.id:04d}")[-4:].upper()

        bits = ["PEAK", code] + ([date_part] if date_part else []) + [suffix]
        return "-".join(bits)

    def headcount(self):
        return sum(i.people for i in self.items())


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    trek_id = db.Column(db.Integer, db.ForeignKey("trek.id"), nullable=True)

    trek_slug = db.Column(db.String(80), nullable=True)
    trek_name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(150), nullable=True)
    image_url = db.Column(db.String(255), nullable=True)
    trek_date = db.Column(db.String(20), nullable=False)

    people = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Integer, nullable=False)

    def subtotal(self):
        return self.price * self.people


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)

    transaction_id = db.Column(db.String(60), unique=True, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False, default="card")
    method = db.Column(db.String(40), nullable=False, default="Test card")
    upi_id = db.Column(db.String(120), nullable=True)

    amount = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False)
    gateway_message = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=now_ist)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.String(400), nullable=False)
    kind = db.Column(db.String(30), nullable=False, default="info")
    link = db.Column(db.String(255), nullable=True)

    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=now_ist)


class Enquiry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), default="")
    subject = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    emailed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now_ist)


# ================================================================
# SESSION / CART / NOTIFICATION HELPERS
# ================================================================
def current_user():
    if session.get("user_id"):
        return db.session.get(User, session["user_id"])
    return None


def login_required(view):
    """Guarantees a real User row before the view runs. A session pointing at a
    deleted or missing user is cleared here rather than surfacing later as a
    NoneType error inside checkout."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            session.pop("user_id", None)
            flash("Sign in to continue.", "info")
            return redirect(url_for("signin", next=request.path))
        g.user = user
        return view(*args, **kwargs)
    return wrapper


def get_cart_key():
    if "cart_key" not in session:
        session["cart_key"] = uuid.uuid4().hex
    return session["cart_key"]


def get_cart():
    return (CartItem.query
            .filter_by(cart_key=get_cart_key())
            .order_by(CartItem.id.asc())
            .all())


def get_cart_count():
    return sum(item.people for item in get_cart())


def get_cart_total():
    return sum(item.subtotal() for item in get_cart())


def merge_cart_into_account(user):
    """Called on sign-in. Claims the guest cart built in this browser for the
    account, and pulls back anything the account had saved under an older cart
    key (for example from before the last sign-out, which rotates the key).
    Rows for the same trek and date are combined instead of duplicated."""
    key = get_cart_key()

    for row in CartItem.query.filter_by(cart_key=key).all():
        row.user_id = user.id

    for row in CartItem.query.filter(CartItem.user_id == user.id,
                                     CartItem.cart_key != key).all():
        row.cart_key = key

    db.session.flush()

    seen = {}
    for row in (CartItem.query.filter_by(cart_key=key)
                .order_by(CartItem.id.asc()).all()):
        signature = (row.trek_id, row.trek_date)
        if signature in seen:
            keeper = seen[signature]
            keeper.people = min(keeper.people + row.people, MAX_PEOPLE)
            db.session.delete(row)
        else:
            seen[signature] = row

    db.session.commit()


def calculate_bill(subtotal):
    gst = round(subtotal * GST_RATE)
    fee = BOOKING_FEE if subtotal > 0 else 0
    return subtotal, gst, fee, subtotal + gst + fee


def notify(user_id, title, message, kind="info", link=None):
    if not user_id:
        return
    db.session.add(Notification(user_id=user_id, title=title, message=message,
                                kind=kind, link=link))
    db.session.commit()


def get_unread_notif_count():
    if not session.get("user_id"):
        return 0
    return Notification.query.filter_by(user_id=session["user_id"],
                                        is_read=False).count()


def get_recent_notifs(limit=8):
    if not session.get("user_id"):
        return []
    return (Notification.query
            .filter_by(user_id=session["user_id"])
            .order_by(Notification.created_at.desc())
            .limit(limit).all())


def get_available_dates(count=8):
    """Next N Saturdays and Sundays in Bengaluru time, as YYYY-MM-DD."""
    today = today_ist()
    dates, cursor = [], today + timedelta(days=1)
    while len(dates) < count:
        if cursor.weekday() in (5, 6):
            dates.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=1)
    return dates


def valid_trek_date(value):
    """Accept only a YYYY-MM-DD string that is a real, non-past date in
    Bengaluru time."""
    try:
        parsed = datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return parsed if parsed >= today_ist() else None


def pretty_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%a, %d %b %Y")
    except (ValueError, TypeError):
        return value


app.jinja_env.filters["pretty_date"] = pretty_date


@app.context_processor
def inject_globals():
    return {
        "current_user": current_user(),
        "cart_count": get_cart_count(),
        "unread_count": get_unread_notif_count(),
        "recent_notifs": get_recent_notifs(),
        "current_year": datetime.now().year,
    }


# ================================================================
# PAYMENT 
# ================================================================
def process_test_card_payment(card_number, expiry, cvv, amount):
    digits = "".join(ch for ch in (card_number or "") if ch.isdigit())

    if len(digits) != 16 or not (cvv or "").strip().isdigit() or not (expiry or "").strip():
        return {"success": False,
                "message": "Those card details look incomplete. Check the number, expiry and CVV."}

    if digits == "4000000000000002":
        return {"success": False, "message": "The bank declined this card."}

    return {"success": True,
            "message": "Payment approved in test mode.",
            "transaction_id": f"TEST-{uuid.uuid4().hex[:12].upper()}"}


def process_test_upi_payment(upi_id, amount):
    upi_id = (upi_id or "").strip()

    if "@" not in upi_id or len(upi_id) < 3:
        return {"success": False, "message": "Enter a UPI ID in the form name@bank."}

    if upi_id.lower().startswith("fail"):
        return {"success": False, "message": "The UPI app declined this payment."}

    return {"success": True,
            "message": "UPI payment approved in test mode.",
            "transaction_id": f"UPI-{uuid.uuid4().hex[:12].upper()}"}


def generate_upi_qr_data_uri(amount, order_ref="PEAK-ORDER"):
    upi_uri = (f"upi://pay?pa={UPI_PAYEE_VPA}&pn={UPI_PAYEE_NAME.replace(' ', '%20')}"
               f"&am={amount}&cu=INR&tn=PEAK%20Booking%20{order_ref}")
    buf = io.BytesIO()
    qrcode.make(upi_uri).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ================================================================
# EMAIL RECEIPT
# ================================================================
ENQUIRY_INBOX = "peak84726@gmail.com"

SUPPORT_EMAIL = ENQUIRY_INBOX
SUPPORT_PHONE = "+91 80 4000 0000"


def deliver(msg, label, text_body=""):
    """Hand a built MIMEMultipart to the SMTP server named in the config and
    report whether it actually left. Used by both the booking receipt and the
    Contact page, so there is one place where mail delivery can go wrong.

    With MAIL_USERNAME / MAIL_PASSWORD set (see the .env notes at the top of
    this file) mail goes out for real. With neither set, it falls back to
    localhost:1025 and, failing that, prints the message to the console so the
    flow can still be demonstrated without a mail server."""
    username = app.config.get("MAIL_USERNAME")
    password = app.config.get("MAIL_PASSWORD")
    try:
        with smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"], timeout=15) as server:
            if username and password:
                if app.config.get("MAIL_USE_TLS", True):
                    server.starttls()
                server.login(username, password)
            server.send_message(msg)
        print(f"[EMAIL] {label} sent to {msg['To']}.")
        return True
    except Exception as exc:
        print(f"[EMAIL] {label} could not be sent ({exc}). Printing it instead:")
        print("------ EMAIL (console fallback) ------")
        print(f"To: {msg['To']}\nSubject: {msg['Subject']}\n{text_body}")
        print("--------------------------------------")
        return False


def send_enquiry_email(enquiry):
    """Contact-page message, delivered to ENQUIRY_INBOX. Reply-To is set to the
    sender, so hitting reply in the inbox answers the person who wrote in."""
    subject = f"[PEAK contact] {enquiry.subject} - {enquiry.name}"

    text_body = (
        f"New message from the PEAK contact form\n"
        f"--------------------------------------\n"
        f"Name:    {enquiry.name}\n"
        f"Email:   {enquiry.email}\n"
        f"Phone:   {enquiry.phone or 'not given'}\n"
        f"Subject: {enquiry.subject}\n"
        f"Sent:    {enquiry.created_at.strftime('%d %b %Y, %I:%M %p') if enquiry.created_at else ''} IST\n"
        f"Ref:     ENQ-{enquiry.id}\n\n"
        f"Message\n-------\n{enquiry.message}\n"
    )

    rows = "".join(
        f'<tr><td style="padding:6px 16px 6px 0;color:#5b6570;font-size:13px;">{k}</td>'
        f'<td style="padding:6px 0;color:#14171c;font-size:14px;font-weight:600;">{v}</td></tr>'
        for k, v in [
            ("Name", enquiry.name),
            ("Email", enquiry.email),
            ("Phone", enquiry.phone or "not given"),
            ("Subject", enquiry.subject),
            ("Reference", f"ENQ-{enquiry.id}"),
        ]
    )

    html_body = f"""<html><body style="margin:0;padding:24px;background:#f4f3f0;
      font-family:-apple-system,Segoe UI,Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="max-width:620px;margin:0 auto;background:#fff;border:1px solid #e3e0da;border-radius:10px;">
        <tr><td style="padding:26px 28px;">
          <p style="margin:0 0 4px;font-size:12px;letter-spacing:1.4px;text-transform:uppercase;color:#5b6570;">
            PEAK contact form</p>
          <h1 style="margin:0 0 20px;font-size:21px;color:#14171c;">New enquiry</h1>
          <table cellpadding="0" cellspacing="0" role="presentation">{rows}</table>
          <div style="margin-top:22px;padding-top:18px;border-top:1px solid #e3e0da;">
            <p style="margin:0 0 8px;font-size:12px;letter-spacing:1.4px;text-transform:uppercase;color:#5b6570;">
              Message</p>
            <p style="margin:0;font-size:15px;line-height:1.7;color:#14171c;white-space:pre-wrap;">{enquiry.message}</p>
          </div>
          <p style="margin:22px 0 0;font-size:13px;color:#5b6570;">
            Reply to this email to answer {enquiry.name} directly.</p>
        </td></tr>
      </table></body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = app.config["MAIL_SENDER"]
    msg["To"] = ENQUIRY_INBOX
    msg["Reply-To"] = enquiry.email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    return deliver(msg, f"Enquiry ENQ-{enquiry.id}", text_body)


def send_enquiry_ack(enquiry):
    """Short acknowledgement to whoever wrote in, so the form does not feel
    like it vanished into nothing. Failure here is not reported to the user -
    the enquiry itself is already saved and delivered."""
    subject = "We have your message - PEAK"
    text_body = (
        f"Hi {enquiry.name.split()[0] if enquiry.name else 'there'},\n\n"
        f"Thanks for writing in. Your message reached us and we reply within one\n"
        f"working day, usually sooner.\n\n"
        f"Your reference is ENQ-{enquiry.id}. What you sent:\n\n"
        f"Subject: {enquiry.subject}\n{enquiry.message}\n\n"
        f"If it is urgent, call {SUPPORT_PHONE} on weekdays between 10am and 7pm.\n\n"
        f"PEAK Adventures, Indiranagar, Bengaluru 560038\n"
    )
    html_body = f"""<html><body style="margin:0;padding:24px;background:#f4f3f0;
      font-family:-apple-system,Segoe UI,Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e3e0da;border-radius:10px;">
        <tr><td style="padding:28px;">
          <h1 style="margin:0 0 14px;font-size:22px;color:#14171c;">We have your message</h1>
          <p style="margin:0 0 14px;font-size:15px;line-height:1.7;color:#14171c;">
            Thanks for writing in. We reply within one working day, usually sooner.
            Your reference is <b>ENQ-{enquiry.id}</b>.</p>
          <p style="margin:0 0 6px;font-size:12px;letter-spacing:1.4px;text-transform:uppercase;color:#5b6570;">
            What you sent</p>
          <p style="margin:0;font-size:14px;line-height:1.7;color:#14171c;white-space:pre-wrap;">{enquiry.message}</p>
          <p style="margin:22px 0 0;font-size:13px;color:#5b6570;">
            Urgent? Call {SUPPORT_PHONE}, weekdays 10am to 7pm.</p>
        </td></tr>
      </table></body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = app.config["MAIL_SENDER"]
    msg["To"] = enquiry.email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    return deliver(msg, f"Acknowledgement for ENQ-{enquiry.id}", text_body)


def email_image_for(item):
    """Emails cannot load a local file path like /kudremukh.jpg, so fall back
    to the trek's hosted photograph when the stored snapshot is a local path."""
    if (item.image_url or "").startswith("http"):
        return item.image_url
    trek = db.session.get(Trek, item.trek_id) if item.trek_id else None
    return trek.fallback_image if trek else ""


def meeting_point_for(item):
    trek = db.session.get(Trek, item.trek_id) if item.trek_id else None
    return trek.starting_point if trek else item.location or ""


def send_receipt_email(order, payment):
    """Booking confirmation. Every figure here is read off the Order, OrderItem
    and Payment rows, so the email, the confirmation page and the database
    always agree."""
    subject = f"Booking confirmed - {order.order_ref} - PEAK"

    ink, muted, line, brand, clay = "#14171c", "#5b6570", "#e3e0da", "#17233a", "#b45332"

    item_blocks = ""
    for item in order.items():
        photo = email_image_for(item)
        img_cell = (f'<img src="{photo}" width="120" height="86" alt="{item.trek_name}" '
                    f'style="display:block;width:120px;height:86px;object-fit:cover;border-radius:8px;border:0;">'
                    if photo else "")
        item_blocks += f"""
        <tr>
          <td style="padding:18px 0;border-bottom:1px solid {line};">
            <table width="100%" cellpadding="0" cellspacing="0" role="presentation"><tr>
              <td width="132" valign="top" style="padding-right:12px;">{img_cell}</td>
              <td valign="top">
                <div style="font-family:Georgia,serif;font-size:17px;color:{ink};">{item.trek_name}</div>
                <div style="font-size:13px;color:{muted};padding-top:4px;">{item.location}</div>
                <div style="font-size:13px;color:{ink};padding-top:8px;">
                  <b>Date:</b> {pretty_date(item.trek_date)}<br>
                  <b>Trekkers:</b> {item.people}<br>
                  <b>Meeting point:</b> {meeting_point_for(item)}
                </div>
              </td>
              <td valign="top" align="right" style="font-size:15px;color:{ink};white-space:nowrap;">
                <b>&#8377;{item.subtotal()}</b>
                <div style="font-size:12px;color:{muted};padding-top:4px;">
                  &#8377;{item.price} &times; {item.people}
                </div>
              </td>
            </tr></table>
          </td>
        </tr>"""

    def money_row(label, value, strong=False):
        weight = "700" if strong else "400"
        color = clay if strong else muted
        size = "17px" if strong else "14px"
        border = f"border-top:1px solid {line};" if strong else ""
        return f"""
        <tr>
          <td style="padding:8px 0;{border}font-size:{size};color:{muted};">{label}</td>
          <td align="right" style="padding:8px 0;{border}font-size:{size};color:{color};font-weight:{weight};">
            &#8377;{value}</td>
        </tr>"""

    txn_rows = f"""
      <tr><td style="font-size:13px;color:{muted};padding:6px 0;">Booking reference</td>
          <td align="right" style="font-size:13px;color:{ink};font-weight:700;">{order.order_ref}</td></tr>
      <tr><td style="font-size:13px;color:{muted};padding:6px 0;">Booked on</td>
          <td align="right" style="font-size:13px;color:{ink};">{order.created_at.strftime('%d %b %Y, %I:%M %p')}</td></tr>
      <tr><td style="font-size:13px;color:{muted};padding:6px 0;">Payment method</td>
          <td align="right" style="font-size:13px;color:{ink};">{payment.method}{f' ({payment.upi_id})' if payment.upi_id else ''}</td></tr>
      <tr><td style="font-size:13px;color:{muted};padding:6px 0;">Transaction ID</td>
          <td align="right" style="font-size:13px;color:{ink};">{payment.transaction_id}</td></tr>
      <tr><td style="font-size:13px;color:{muted};padding:6px 0;">Contact number</td>
          <td align="right" style="font-size:13px;color:{ink};">{order.phone}</td></tr>"""

    html_body = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f6f4f1;font-family:Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" role="presentation"><tr><td align="center" style="padding:32px 14px;">
  <table width="600" cellpadding="0" cellspacing="0" role="presentation"
         style="background:#ffffff;border:1px solid {line};border-radius:14px;overflow:hidden;">

    <tr><td style="background:{brand};padding:22px 32px;">
      <span style="font-family:Georgia,serif;font-size:22px;color:#ffffff;letter-spacing:.5px;">PEAK</span>
      <span style="font-size:12px;color:#c6cedd;padding-left:10px;">Karnataka trekking</span>
    </td></tr>

    <tr><td style="padding:34px 32px 6px;">
      <h1 style="margin:0 0 8px;font-family:Georgia,serif;font-size:26px;color:{ink};font-weight:normal;">
        Booking Confirmed</h1>
      <p style="margin:0;font-size:14px;color:{muted};line-height:1.6;">
        {order.name}, your payment went through and your slot is held.
        Keep this email; the booking reference is your ticket on trek day.</p>
    </td></tr>

    <tr><td style="padding:22px 32px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="background:#edeae4;border-radius:10px;">
        <tr><td style="padding:16px 18px;">
          <table width="100%" cellpadding="0" cellspacing="0" role="presentation">{txn_rows}</table>
        </td></tr>
      </table>
    </td></tr>

    <tr><td style="padding:26px 32px 0;">
      <div style="font-size:12px;color:{muted};letter-spacing:.6px;padding-bottom:4px;">YOUR TREKS</div>
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation">{item_blocks}</table>
    </td></tr>

    <tr><td style="padding:18px 32px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
        {money_row('Subtotal', order.subtotal)}
        {money_row('GST (5%)', order.gst)}
        {money_row('Booking fee', order.booking_fee)}
        {money_row('Total paid', order.total, strong=True)}
      </table>
    </td></tr>

    <tr><td style="padding:28px 32px 0;">
      <div style="border:1px solid {line};border-radius:10px;padding:18px 20px;">
        <div style="font-size:14px;color:{ink};font-weight:700;padding-bottom:10px;">Before you travel</div>
        <div style="font-size:13px;color:{muted};line-height:1.8;">
          1. Reach the meeting point 30 minutes before the listed start time.<br>
          2. Carry a government photo ID in the name on this booking; forest checkposts verify it.<br>
          3. Wear shoes with grip and carry at least two litres of water.<br>
          4. Cancellations and date changes are free up to 72 hours before departure.<br>
          5. Your guide's phone number is sent two days before the trek.
        </div>
      </div>
    </td></tr>

    <tr><td style="padding:26px 32px 34px;">
      <div style="font-size:13px;color:{muted};line-height:1.7;">
        Questions about this booking? Reply to this email, write to
        <a href="mailto:{SUPPORT_EMAIL}" style="color:{brand};">{SUPPORT_EMAIL}</a>,
        or call {SUPPORT_PHONE} on weekdays between 10am and 7pm.
      </div>
    </td></tr>

    <tr><td style="background:#edeae4;padding:16px 32px;font-size:12px;color:{muted};">
      PEAK Adventures, Indiranagar, Bengaluru 560038
    </td></tr>
  </table>
</td></tr></table>
</body></html>"""

    item_lines = "\n".join(
        f"  - {i.trek_name} ({i.location})\n"
        f"    Date: {pretty_date(i.trek_date)} | Trekkers: {i.people} | "
        f"Meeting point: {meeting_point_for(i)}\n"
        f"    Rs {i.price} x {i.people} = Rs {i.subtotal()}"
        for i in order.items())

    text_body = f"""PEAK - Booking Confirmed

{order.name}, your payment went through and your slot is held.

Booking reference : {order.order_ref}
Booked on         : {order.created_at.strftime('%d %b %Y, %I:%M %p')}
Payment method    : {payment.method}{f' ({payment.upi_id})' if payment.upi_id else ''}
Transaction ID    : {payment.transaction_id}
Contact number    : {order.phone}

YOUR TREKS
{item_lines}

Subtotal    : Rs {order.subtotal}
GST (5%)    : Rs {order.gst}
Booking fee : Rs {order.booking_fee}
TOTAL PAID  : Rs {order.total}

BEFORE YOU TRAVEL
1. Reach the meeting point 30 minutes before the listed start time.
2. Carry a government photo ID in the name on this booking.
3. Wear shoes with grip and carry at least two litres of water.
4. Cancellations and date changes are free up to 72 hours before departure.
5. Your guide's phone number is sent two days before the trek.

Questions? Reply to this email, write to {SUPPORT_EMAIL}, or call {SUPPORT_PHONE}
on weekdays between 10am and 7pm.

PEAK Adventures, Indiranagar, Bengaluru 560038
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = app.config["MAIL_SENDER"]
    msg["To"] = order.email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    username = app.config.get("MAIL_USERNAME")
    password = app.config.get("MAIL_PASSWORD")

    try:
        with smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"], timeout=10) as server:
            if username and password:
                if app.config.get("MAIL_USE_TLS", True):
                    server.starttls()
                server.login(username, password)
            server.send_message(msg)
        print(f"[EMAIL] Receipt for {order.order_ref} sent to {order.email}.")
    except Exception as exc:
        print(f"[EMAIL] Send failed ({exc}). Printing receipt instead:")
        print("------ EMAIL RECEIPT (console fallback) ------")
        print(f"To: {order.email}\nSubject: {subject}\n{text_body}")
        print("---------------------------------------------")


# ================================================================
# TEMPLATES
# ----------------------------------------------------------------

TEMPLATES = {}

TEMPLATES["base.html"] = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}PEAK{% endblock %}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400..700&family=Plus+Jakarta+Sans:wght@300..800&display=swap" rel="stylesheet">
<style>
:root{
  /* ---------------------------------------------------------------
     PEAK dark system.
     Ink base (near-black with a blue cast), glacier teal as the single
     interactive accent, ember orange reserved for money and kickers.
     Every component below reads from these tokens, so the palette can
     be retuned in one place without touching any page.
     --------------------------------------------------------------- */
  --bg:#07090c;
  --bg-2:#0a0d11;
  --surface:#11151b;
  --surface-2:#0c1015;
  --surface-3:#171c23;
  --stone:#1b2027;
  --fill:#161b21;

  /* ONE colour family only: white on near-black. Nothing is coloured.
     Hierarchy is carried by SIZE, WEIGHT, OPACITY and BORDER strength,
     never by hue, so the whole site reads as a single neutral system. */
  --brand:#ffffff;
  --brand-dark:#e8e8e8;
  --brand-light:#ffffff;
  --brand-ink:#0a0d12;
  --brand-soft:rgba(255,255,255,.10);

  --accent:#ffffff;
  --accent-soft:rgba(255,255,255,.10);
  --green:#ffffff;
  --red:#ffffff;

  --text:#f4f6f8;
  --text-2:#c6cdd4;
  --muted:#8b949e;

  /* the single uniform hairline used on every button, box and panel */
  --line:rgba(255,255,255,.22);
  --line-strong:rgba(255,255,255,.34);

  --shadow-sm:0 1px 2px rgba(0,0,0,.45);
  --shadow:0 2px 6px rgba(0,0,0,.35),0 18px 44px rgba(0,0,0,.45);
  --shadow-lg:0 34px 80px rgba(0,0,0,.62);
  --ring:0 0 0 1px rgba(255,255,255,.34);
  --glow:0 0 0 1px rgba(255,255,255,.3),0 18px 46px rgba(255,255,255,.06);

  --r-sm:12px; --r-md:16px; --r-lg:22px; --r-xl:28px; --r-2xl:34px; --r-full:999px;
  /* Plus Jakarta Sans carries the UI and body copy. Space Grotesk gives
     headings a sharper, more distinctive display face. */
  --sans:'Plus Jakarta Sans',system-ui,sans-serif;
  --serif:'Space Grotesk','Plus Jakarta Sans',system-ui,sans-serif;
  --pad:clamp(20px,4vw,64px);
  --gap:clamp(22px,2vw,32px);
  --glass:rgba(255,255,255,.045);
  --shell:1560px;
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%;background:var(--bg);color-scheme:dark}
body{font-family:var(--sans);color:var(--text);font-size:16.5px;line-height:1.7;font-weight:400;
  -webkit-font-smoothing:antialiased;overflow-x:hidden;
  background:
    radial-gradient(1100px 620px at 8% -8%,rgba(255,255,255,.05),transparent 62%),
    radial-gradient(900px 560px at 96% 4%,rgba(255,255,255,.035),transparent 60%),
    var(--bg);
  background-attachment:fixed}
a{color:inherit}
img{max-width:100%;display:block}
/* 9) every photograph on the site fills the box it is given and is
   anchored dead centre, so nothing is ever cropped off to one side. */
img{object-fit:cover;object-position:center center}
::selection{background:rgba(255,255,255,.26);color:#fff}
:focus-visible{outline:2px solid var(--brand);outline-offset:3px;border-radius:6px}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

/* ---------- type ---------- */
h1,h2,h3,h4{font-family:var(--serif);font-weight:600;line-height:1.08;letter-spacing:-.8px;color:var(--text)}
.display{font-size:clamp(46px,6.2vw,92px);font-weight:700;line-height:.98;letter-spacing:-3px}
h1{font-size:clamp(34px,4.6vw,58px);letter-spacing:-1.4px}
h2{font-size:clamp(28px,3.2vw,44px);letter-spacing:-1.1px}
h3{font-size:22px;letter-spacing:-.5px}
h4{font-size:17px;letter-spacing:-.3px}
p{max-width:74ch}
.lede{color:var(--text-2);font-size:18px;line-height:1.75;max-width:62ch}
.small{font-size:13.5px;color:var(--muted);line-height:1.65}
.kicker{display:inline-block;color:var(--muted);font-size:12px;font-weight:700;
  letter-spacing:2px;text-transform:uppercase;margin-bottom:14px}
.serif-i{font-style:italic}
.tint{color:#fff;font-weight:700}

/* ---------- layout ---------- */
.shell{max-width:var(--shell);margin:0 auto;padding-left:var(--pad);padding-right:var(--pad);width:100%}
.shell--narrow{max-width:980px}
.section{padding:clamp(66px,8vw,118px) 0}
.section--tight{padding:clamp(40px,5vw,68px) 0}
.section--surface{background:var(--surface-2);border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.head{max-width:720px;margin-bottom:clamp(34px,4vw,56px)}
.head--center{margin-left:auto;margin-right:auto;text-align:center}
.grid{display:grid;gap:var(--gap)}
.g-2{grid-template-columns:repeat(auto-fit,minmax(360px,1fr))}
.g-3{grid-template-columns:repeat(auto-fit,minmax(360px,1fr))}
.g-4{grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}
.row{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.row--between{justify-content:space-between}
.spacer{flex:1}

/* ---------- buttons ---------- */
/* 7) EVERY button carries the same 1px white hairline. The three variants
   differ only in fill and text weight, never in colour. */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:9px;padding:15px 30px;
  border:1px solid var(--line-strong);border-radius:var(--r-sm);font:inherit;font-size:14.5px;font-weight:700;
  line-height:1.2;letter-spacing:.1px;text-decoration:none;cursor:pointer;
  transition:background .18s ease,color .18s ease,border-color .18s ease,box-shadow .18s ease,transform .18s ease}
.btn--primary{background:#fff;color:var(--brand-ink);border:1px solid #fff;font-weight:800;
  box-shadow:0 10px 28px rgba(0,0,0,.45)}
.btn--primary:hover{transform:translateY(-1px);background:#eef1f4;border-color:#eef1f4;
  box-shadow:0 16px 38px rgba(0,0,0,.55)}
.btn--ghost{background:var(--glass);border-color:var(--line-strong);color:var(--text)}
.btn--ghost:hover{border-color:#fff;background:rgba(255,255,255,.12);box-shadow:var(--ring)}
.btn--outline{background:transparent;border-color:var(--line-strong);color:var(--text)}
.btn--outline:hover{background:rgba(255,255,255,.12);border-color:#fff;box-shadow:var(--ring)}
.btn--sm{padding:11px 22px;font-size:13.5px}
.btn--wide{width:100%}
.btn--danger{background:none;border:1px solid var(--line);color:var(--muted);padding:9px 16px;
  font-size:12.5px;font-weight:600}
.btn--danger:hover{border-color:#fff;color:var(--text)}

/* ---------- surfaces ---------- */
.card{background:linear-gradient(180deg,rgba(255,255,255,.035),rgba(255,255,255,0)),var(--surface);
  border:1px solid var(--line);border-radius:var(--r-xl);
  padding:clamp(26px,2.4vw,36px);box-shadow:var(--shadow)}
.card--flat{box-shadow:none}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:28px}
.pill{display:inline-flex;align-items:center;gap:6px;padding:7px 15px;border-radius:var(--r-full);
  font-size:12.5px;font-weight:600;letter-spacing:.1px;
  border:1px solid var(--line-strong);color:var(--text-2);background:rgba(255,255,255,.05)}
.pill--muted{color:var(--muted);border-color:var(--line)}
/* status pills: separated by weight and border strength, not by colour */
.pill--brand{border-color:#fff;color:var(--text);background:rgba(255,255,255,.12);font-weight:700}
.pill--ok{border-color:#fff;color:#fff;background:rgba(255,255,255,.16);font-weight:800}
.pill--bad{border-color:var(--line);color:var(--muted);background:transparent;font-weight:600;
  text-decoration:line-through}
.divider{height:1px;background:var(--line);border:0;margin:32px 0}

/* ---------- navbar ---------- */
.nav{position:sticky;top:0;z-index:200;height:82px;display:flex;align-items:center;justify-content:space-between;
  gap:20px;padding:0 var(--pad);background:rgba(8,11,17,.78);backdrop-filter:blur(18px) saturate(1.3);
  border-bottom:1px solid var(--line)}
.brand{font-family:var(--serif);font-size:27px;font-weight:600;letter-spacing:.6px;text-decoration:none;color:var(--text)}
.brand i{color:var(--text);font-style:normal}
.nav-links{display:flex;align-items:center;gap:34px}
.nav-links a.navlink{position:relative;color:var(--muted);text-decoration:none;font-size:14.5px;font-weight:500;
  padding:6px 0;transition:color .18s}
.nav-links a.navlink::after{content:"";position:absolute;left:0;right:100%;bottom:0;height:2px;
  background:#fff;transition:right .22s ease}
.nav-links a.navlink:hover,.nav-links a.navlink.on{color:var(--text)}
.nav-links a.navlink:hover::after,.nav-links a.navlink.on::after{right:0}
.nav-tools{display:flex;align-items:center;gap:12px}
.icon-btn{position:relative;display:inline-flex;align-items:center;gap:8px;padding:10px 16px;border:1px solid var(--line-strong);
  border-radius:var(--r-sm);background:rgba(255,255,255,.04);color:var(--text);text-decoration:none;
  font-size:13.5px;font-weight:600;cursor:pointer;font-family:inherit;transition:border-color .18s,color .18s,background .18s}
.icon-btn:hover{border-color:#fff;color:var(--text);background:rgba(255,255,255,.12)}
.count{display:inline-flex;align-items:center;justify-content:center;min-width:19px;height:19px;padding:0 5px;
  background:#fff;color:var(--brand-ink);border-radius:var(--r-full);font-size:11px;font-weight:800}
.avatar{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;
  background:rgba(255,255,255,.12);border:1px solid var(--line-strong);
  color:var(--text);font-size:12.5px;font-weight:800;letter-spacing:.5px;cursor:pointer;font-family:inherit}
.menu-wrap{position:relative}
.menu{display:none;position:absolute;top:52px;right:0;width:268px;background:var(--surface-3);
  border:1px solid var(--line-strong);border-radius:var(--r-lg);box-shadow:var(--shadow-lg);overflow:hidden;z-index:300}
.menu.open{display:block}
.menu a,.menu .menu-head{display:block;padding:15px 18px;text-decoration:none;font-size:13.5px;border-bottom:1px solid var(--line)}
.menu a{color:var(--text);font-weight:500}
.menu a:hover{background:rgba(255,255,255,.1);color:#fff}
.menu .menu-head{color:var(--muted);font-size:12.5px;background:rgba(255,255,255,.03)}
.menu a:last-child{border-bottom:0}
.notif{width:350px;max-height:420px;overflow-y:auto}
.notif .item{display:block;padding:16px 18px;border-bottom:1px solid var(--line);text-decoration:none;color:var(--text)}
.notif .item:hover{background:rgba(255,255,255,.05)}
.notif .item.unread{background:rgba(255,255,255,.08)}
.notif .item.unread b{font-weight:800}
.notif .item b{display:block;font-size:13.5px;margin-bottom:4px}
.notif .item span{font-size:12.5px;color:var(--muted);line-height:1.55}
.notif .none{padding:30px;text-align:center;color:var(--muted);font-size:13.5px}
.burger{display:none;background:rgba(255,255,255,.04);border:1px solid var(--line-strong);color:var(--text);
  border-radius:var(--r-sm);padding:10px 13px;font-size:16px;cursor:pointer}
.drawer{display:none;position:fixed;inset:82px 0 0;background:var(--bg-2);z-index:190;padding:30px var(--pad);overflow-y:auto}
.drawer.open{display:block}
.drawer a{display:block;padding:18px 0;border-bottom:1px solid var(--line);text-decoration:none;
  color:var(--text);font-family:var(--serif);font-size:26px;letter-spacing:-.6px}
@media (max-width:1000px){
  .nav-links{display:none}
  .burger{display:inline-block}
}
@media (max-width:560px){
  .nav{height:72px}
  .drawer{inset:72px 0 0}
  .icon-btn{padding:10px 13px}
}

/* ---------- flash ---------- */
.flashes{position:fixed;top:100px;right:22px;z-index:400;display:flex;flex-direction:column;gap:12px;max-width:380px}
.flash{display:flex;gap:12px;align-items:flex-start;padding:16px 18px;border-radius:var(--r-md);font-size:13.5px;
  line-height:1.55;background:var(--surface-3);color:var(--text);border:1px solid var(--line-strong);
  border-left:3px solid var(--brand);box-shadow:var(--shadow-lg)}
/* success / error are told apart by border thickness, not colour */
.flash.success{border-left-width:3px;border-left-color:#fff}
.flash.error{border-left-width:6px;border-left-color:#fff}
.flash button{background:none;border:0;color:var(--muted);cursor:pointer;font-size:16px;line-height:1;padding:0 2px}

/* ---------- forms ---------- */
.field{margin-bottom:20px}
.field label{display:block;font-size:13.5px;font-weight:600;margin-bottom:9px;color:var(--text-2)}
.field input,.field select,.field textarea{width:100%;padding:15px 16px;background:var(--surface-2);
  border:1px solid var(--line-strong);border-radius:var(--r-sm);color:var(--text);font-family:inherit;
  font-size:15px;outline:none;transition:border-color .18s,box-shadow .18s,background .18s}
.field textarea{min-height:150px;resize:vertical;line-height:1.6}
.field input:focus,.field select:focus,.field textarea:focus{border-color:#fff;
  background:var(--surface);box-shadow:0 0 0 3px rgba(255,255,255,.14)}
.field input::placeholder,.field textarea::placeholder{color:#6d7c8d}
.field select option{background:var(--surface-3);color:var(--text)}
.field .hint{font-size:12.5px;color:var(--muted);margin-top:8px}
.field-row{display:flex;gap:18px}
.field-row .field{flex:1}
@media (max-width:560px){.field-row{flex-direction:column;gap:0}}

/* ---------- trek card (home + listing only) ---------- */
.trek-card{display:flex;flex-direction:column;position:relative;
  background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(255,255,255,0)),var(--surface);
  border:1px solid var(--line);border-radius:var(--r-2xl);overflow:hidden;box-shadow:var(--shadow);
  transition:box-shadow .3s ease,transform .3s ease,border-color .3s ease}
.trek-card:hover{transform:translateY(-6px);border-color:#fff;
  box-shadow:var(--shadow-lg),0 0 0 1px rgba(255,255,255,.2)}
.trek-card .shot{position:relative;display:block;aspect-ratio:16/10;overflow:hidden;background:var(--stone)}
.trek-card .shot img{width:100%;height:100%;object-fit:cover;object-position:center center;
  transition:transform .7s ease}
.trek-card:hover .shot img{transform:scale(1.06)}
.trek-card .shot::after{content:"";position:absolute;inset:0;
  background:linear-gradient(180deg,rgba(7,10,15,.5) 0%,rgba(7,10,15,0) 42%,rgba(7,10,15,.55) 100%)}
.trek-card .tags{position:absolute;inset:18px 18px auto 18px;display:flex;justify-content:space-between;gap:10px;z-index:2}
.trek-card .tags .pill{background:rgba(9,13,19,.72);backdrop-filter:blur(10px);
  border-color:rgba(255,255,255,.22);color:#eaf1f8}
.trek-card .body{padding:clamp(26px,2.1vw,34px);display:flex;flex-direction:column;flex:1}
.trek-card .where{font-size:13px;color:var(--muted);letter-spacing:.5px;text-transform:uppercase;
  font-weight:600;margin-bottom:10px}
.trek-card h3{margin-bottom:14px;font-size:clamp(26px,1.9vw,31px);letter-spacing:-.9px}
.trek-card .desc{color:var(--text-2);font-size:15px;line-height:1.7;margin-bottom:30px;flex:1}
.specs{display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.35fr) minmax(0,.8fr);
  gap:10px;padding:22px 0;
  border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin-bottom:26px}
.specs div{text-align:center;min-width:0;padding:0 2px}
.specs span{display:block;font-size:11px;letter-spacing:.9px;text-transform:uppercase;
  color:var(--muted);margin-bottom:6px;white-space:nowrap}
.specs b{display:block;font-size:14.5px;font-weight:700;color:var(--text);line-height:1.35}
.specs div:nth-child(2) b{font-size:14px;white-space:nowrap}
.specs div:nth-child(3) b{white-space:nowrap}
@media (max-width:520px){.specs b,.specs div:nth-child(2) b{white-space:normal}}
/* price: no longer orange. It stands out by being the largest, heaviest
   number in its row, in plain white. */
.price{font-size:29px;font-weight:800;color:#fff;font-family:var(--sans);letter-spacing:-.8px}
.price sub{font-size:12px;color:var(--muted);font-weight:500;vertical-align:baseline}
.card-foot{margin-top:auto;gap:14px;flex-wrap:nowrap}
.card-foot .btn{white-space:nowrap}
@media (max-width:400px){.card-foot{flex-wrap:wrap}}

/* ---------- misc ---------- */
.stat b{display:block;font-family:var(--serif);font-size:40px;letter-spacing:-1.2px;color:var(--text)}
.stat span{font-size:13.5px;color:var(--muted)}
.ticklist{list-style:none;display:grid;gap:13px}
.ticklist + .kicker,.ticklist + h2,.ticklist + h3,.ticklist + h4{margin-top:clamp(26px,4vw,44px)}
.ticklist li{position:relative;padding-left:26px;font-size:14.5px;line-height:1.65;color:var(--text-2)}
.ticklist li::before{content:"";position:absolute;left:0;top:10px;width:8px;height:8px;border-radius:2px;background:#fff}
.ticklist.no li::before{background:transparent;border:1px solid var(--line-strong);border-radius:2px}
.ticklist.no li{color:var(--muted)}
.empty{text-align:center;padding:clamp(60px,8vw,96px) 30px}
.empty h2{margin-bottom:14px;font-size:30px}
.empty p{color:var(--muted);margin:0 auto 30px;max-width:46ch}
.line{display:flex;justify-content:space-between;gap:18px;font-size:14.5px;color:var(--muted);margin-bottom:14px}
.line b{color:var(--text);font-weight:600}
.line--total{padding-top:18px;margin-top:10px;border-top:1px solid var(--line);font-size:19px;font-weight:700;color:var(--text)}
.line--total b{color:#fff;font-size:23px;font-weight:800}

/* ---------- footer ---------- */
footer{background:var(--surface-2);border-top:1px solid var(--line);color:var(--text-2);
  padding:clamp(60px,7vw,92px) 0 34px;margin-top:0}
footer .brand{color:var(--text)}
footer .brand i{color:var(--text)}
footer .small{color:var(--muted)}
.foot-grid{display:grid;grid-template-columns:1.8fr 1fr 1fr 1fr;gap:44px;
  padding-bottom:48px;border-bottom:1px solid var(--line)}
.foot-grid h4{font-family:var(--sans);font-size:12.5px;font-weight:700;color:var(--text);
  letter-spacing:1.2px;text-transform:uppercase;margin-bottom:18px}
.foot-grid a{display:block;color:var(--muted);text-decoration:none;font-size:14.5px;margin-bottom:12px;transition:color .18s}
.foot-grid a:hover{color:#fff}
.foot-bottom{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;padding-top:28px;
  font-size:13.5px;color:var(--muted)}
@media (max-width:900px){.foot-grid{grid-template-columns:1fr 1fr;gap:34px}}
@media (max-width:560px){
  .foot-grid{grid-template-columns:1fr}
  .flashes{left:14px;right:14px;top:86px;max-width:none}
}
{% block extra_css %}{% endblock %}
</style>
</head>
<body>

<header class="nav">
  <a href="/" class="brand">PEAK<i>.</i></a>

  <nav class="nav-links">
    <a class="navlink {{ 'on' if nav == 'home' }}" href="/">Home</a>
    <a class="navlink {{ 'on' if nav == 'treks' }}" href="/treks">All treks</a>
    <a class="navlink {{ 'on' if nav == 'about' }}" href="/about">About us</a>
    <a class="navlink {{ 'on' if nav == 'contact' }}" href="/contact">Contact</a>
  </nav>

  <div class="nav-tools">
    <a href="/cart" class="icon-btn" aria-label="Cart">Cart{% if cart_count %}<span class="count">{{ cart_count }}</span>{% endif %}</a>

    {% if current_user %}
      <div class="menu-wrap">
        <button class="icon-btn" onclick="toggleMenu(event,'notifMenu')" aria-label="Notifications">
          Alerts{% if unread_count %}<span class="count">{{ unread_count }}</span>{% endif %}
        </button>
        <div class="menu notif" id="notifMenu">
          {% for n in recent_notifs %}
            <a class="item {{ 'unread' if not n.is_read }}" href="/notifications/open/{{ n.id }}">
              <b>{{ n.title }}</b><span>{{ n.message }}</span>
            </a>
          {% else %}
            <div class="none">Nothing here yet. Book a trek and updates will show up.</div>
          {% endfor %}
        </div>
      </div>

      <div class="menu-wrap">
        <button class="avatar" onclick="toggleMenu(event,'userMenu')" aria-label="Account">{{ current_user.initials() }}</button>
        <div class="menu" id="userMenu">
          <div class="menu-head">Signed in as {{ current_user.email }}</div>
          <a href="/bookings">My bookings</a>
          <a href="/cart">My cart</a>
          <a href="/logout">Sign out</a>
        </div>
      </div>
    {% else %}
      <a href="/signin" class="btn btn--outline btn--sm">Sign in</a>
    {% endif %}

    <button class="burger" onclick="toggleDrawer()" aria-label="Menu">&#9776;</button>
  </div>
</header>

<div class="drawer" id="drawer">
  <a href="/">Home</a>
  <a href="/treks">All treks</a>
  <a href="/about">About us</a>
  <a href="/contact">Contact</a>
  <a href="/cart">Cart{% if cart_count %} ({{ cart_count }}){% endif %}</a>
  {% if current_user %}<a href="/bookings">My bookings</a><a href="/logout">Sign out</a>
  {% else %}<a href="/signin">Sign in</a>{% endif %}
</div>

<div class="flashes">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, message in messages %}
      <div class="flash {{ category }}">
        <span>{{ message }}</span>
        <button onclick="this.parentElement.remove()" aria-label="Dismiss">&times;</button>
      </div>
    {% endfor %}
  {% endwith %}
</div>

{% block body %}{% endblock %}

<footer>
  <div class="shell">
    <div class="foot-grid">
      <div>
        <a href="/" class="brand">PEAK<i>.</i></a>
        <p class="small" style="margin-top:12px;max-width:34ch">
          Guided weekend treks across the Western Ghats and the Deccan plateau,
          operating out of Bengaluru since 2021.
        </p>
      </div>
      <div>
        <h4>Explore</h4>
        <a href="/treks">All treks</a>
        <a href="/treks?sort=price">Lowest price first</a>
        <a href="/treks?sort=rating">Highest rated</a>
        <a href="/treks?q=Western%20Ghats">Western Ghats</a>
      </div>
      <div>
        <h4>Company</h4>
        <a href="/about">About us</a>
        <a href="/contact">Contact</a>
      </div>
      <div>
        <h4>Your account</h4>
        <a href="/bookings">My bookings</a>
        <a href="/cart">Cart</a>
        {% if current_user %}<a href="/logout">Sign out</a>{% else %}<a href="/signin">Sign in</a><a href="/signup">Create account</a>{% endif %}
      </div>
    </div>
    <div class="foot-bottom">
      <span>&copy; {{ current_year }} PEAK Adventures, Bengaluru.</span>
      <span>All treks operated under Karnataka Forest Department permits.</span>
    </div>
  </div>
</footer>

<script>
function toggleMenu(e,id){
  e.stopPropagation();
  document.querySelectorAll('.menu').forEach(function(m){ if(m.id!==id) m.classList.remove('open'); });
  document.getElementById(id).classList.toggle('open');
}
function toggleDrawer(){ document.getElementById('drawer').classList.toggle('open'); }
document.addEventListener('click',function(){
  document.querySelectorAll('.menu').forEach(function(m){ m.classList.remove('open'); });
});
setTimeout(function(){
  document.querySelectorAll('.flash').forEach(function(f){ f.remove(); });
}, 6000);
</script>
{% block extra_js %}{% endblock %}
</body>
</html>
"""


TEMPLATES["home.html"] = """
{% extends "base.html" %}
{% block title %}PEAK — weekend treks across Karnataka{% endblock %}

{% block extra_css %}
/* ---------- opening hero (home page only) ---------- */
.hero{position:relative;isolation:isolate;min-height:min(94vh,940px);display:flex;align-items:center;
  padding:clamp(88px,11vh,140px) var(--pad) clamp(60px,8vh,100px);overflow:hidden;
  border-bottom:1px solid var(--line)}
/* 9) hero photo is centred and covers the whole band */
.hero-bg{position:absolute;inset:0;z-index:-2;background-image:url("/top photo.jpg"),url("{{ hero_photo }}");
  background-size:cover;background-position:center center;background-repeat:no-repeat;
  filter:saturate(1.02) contrast(1.04)}
.hero-veil{position:absolute;inset:0;z-index:-1;
  background:
    linear-gradient(90deg,rgba(5,8,12,.25) 0%,rgba(5,8,12,.1) 34%,rgba(5,8,12,.46) 66%,rgba(5,8,12,.68) 100%),
    linear-gradient(180deg,rgba(5,8,12,.25) 0%,rgba(5,8,12,.10) 34%,rgba(5,8,12,.55) 72%,var(--bg) 100%)}
.hero-glow{position:absolute;inset:auto -10% -40% auto;width:60vw;height:60vw;z-index:-1;pointer-events:none;
  background:radial-gradient(circle,rgba(255,255,255,.07),transparent 62%)}
.hero-inner{position:relative;z-index:2;width:100%;max-width:var(--shell);margin:0 auto}
.hero .eyebrow{display:inline-flex;align-items:center;gap:10px;padding:9px 18px;margin-bottom:26px;
  border-radius:var(--r-full);font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase;
  color:#fff;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.34);
  backdrop-filter:blur(8px)}
.hero .eyebrow .dot{width:7px;height:7px;border-radius:50%;background:#fff}
.hero .display{max-width:15ch;margin-bottom:24px;color:#fff;
  text-shadow:0 2px 40px rgba(0,0,0,.65),0 1px 3px rgba(0,0,0,.5)}
.hero .display em{font-style:normal;color:#fff}
.hero p.sub{max-width:52ch;color:#dbe6ef;font-size:clamp(17px,1.35vw,20px);line-height:1.7;margin-bottom:38px;
  text-shadow:0 1px 18px rgba(0,0,0,.7)}
.hero .btn--ghost{background:rgba(255,255,255,.08);border:1.5px solid rgba(255,255,255,.75);color:#fff;
  backdrop-filter:blur(8px)}
.hero .btn--ghost:hover{background:rgba(255,255,255,.16);border-color:#fff;color:#fff}
.hero-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:clamp(18px,2vw,30px);
  margin-top:clamp(44px,6vh,72px);padding:clamp(22px,2.2vw,30px) clamp(24px,2.6vw,38px);
  border:1px solid rgba(255,255,255,.14);border-radius:var(--r-xl);
  background:rgba(9,13,19,.52);backdrop-filter:blur(16px);box-shadow:var(--shadow-lg)}
.hero-stats .stat b{color:#fff;font-size:clamp(28px,2.4vw,40px)}
.hero-stats .stat span{color:#a9b8c6;font-size:13px}
.hero-scroll{position:absolute;left:50%;bottom:26px;transform:translateX(-50%);z-index:2;
  color:#8fa0b0;font-size:11.5px;letter-spacing:2px;text-transform:uppercase;text-decoration:none}
@media (max-width:760px){
  .hero{min-height:auto;padding-top:clamp(70px,12vh,110px)}
  .hero .display{max-width:none}
  .hero-scroll{display:none}
}

/* ---------- home sections ---------- */
.steps{counter-reset:s;display:grid;gap:var(--gap);grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.step{position:relative;padding:46px 34px 36px;
  background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(255,255,255,0)),var(--surface);
  border:1px solid var(--line);border-radius:var(--r-xl);box-shadow:var(--shadow)}
.step::before{counter-increment:s;content:counter(s);position:absolute;top:-21px;left:34px;width:42px;height:42px;
  display:grid;place-items:center;border-radius:50%;
  background:#fff;border:1px solid #fff;color:var(--brand-ink);
  font-weight:800;font-size:15px;box-shadow:0 10px 24px rgba(0,0,0,.5)}
.step h3{font-size:21px;margin:0 0 12px}
.step p{color:var(--text-2);font-size:14.5px;line-height:1.7}
.quote{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-xl);
  padding:36px 32px;box-shadow:var(--shadow);position:relative;overflow:hidden}
.quote::before{content:"";position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,rgba(255,255,255,.75),transparent)}
.quote p{font-family:var(--serif);font-size:21px;line-height:1.5;letter-spacing:-.5px;margin-bottom:26px;color:var(--text)}
.quote .who{display:flex;align-items:center;gap:12px}
.quote .who .avatar{width:38px;height:38px;font-size:13px}
.quote .who b{display:block;font-size:14px}
.quote .who span{font-size:12px;color:var(--muted)}
.season{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1px;background:var(--line);
  border:1px solid var(--line);border-radius:var(--r-xl);overflow:hidden}
.season div{background:var(--surface);padding:34px 30px;transition:background .25s}
.season div:hover{background:var(--surface-3)}
.season h4{font-family:var(--serif);font-size:22px;margin-bottom:12px;color:#fff;font-weight:700}
.season p{font-size:14px;line-height:1.7;color:var(--text-2)}
/* 8) "Book a weekend departure" panel now uses booktrek.jpg, centred and
   covering the full box, behind a readable scrim. 7) 1px white hairline. */
.cta{position:relative;margin:0 var(--pad) clamp(70px,8vw,120px);padding:clamp(64px,9vw,120px) 34px;
  border-radius:var(--r-2xl);text-align:center;
  border:1px solid var(--line-strong);overflow:hidden;isolation:isolate;
  background-image:linear-gradient(180deg,rgba(5,7,10,.62),rgba(5,7,10,.78)),
                   url("{{ cta_photo }}"),url("{{ cta_photo_fallback }}");
  background-size:cover;background-position:center center;background-repeat:no-repeat;
  box-shadow:var(--shadow-lg)}
.cta h2{max-width:20ch;margin:0 auto 16px;color:#fff}
.cta p{color:#d6e2ec;font-size:17px;max-width:54ch;margin:0 auto 38px}
{% endblock %}

{% block body %}
<section class="hero">
  <div class="hero-bg"></div>
  <div class="hero-veil"></div>
  <div class="hero-glow"></div>
  <div class="hero-inner">
    <span class="eyebrow"><span class="dot"></span>Departures every Saturday and Sunday</span>
    <h1 class="display">Some weekends need a little altitude.</h1>
    <p class="sub">
      Guided weekend treks in Karnataka. {{ trek_count }} trails, batches capped at fifteen, two guides
      on every departure, and permits and transport already in the price.
    </p>
    <div class="row">
      <a href="/treks" class="btn btn--primary">Browse treks</a>
      <a href="#how" class="btn btn--ghost">How booking works</a>
      <a href="#grades" class="btn btn--ghost">Which grade suits me</a>
    </div>

    <div class="hero-stats">
      <div class="stat"><b>{{ trek_count }}</b><span>Trails running this season</span></div>
      <div class="stat"><b>{{ trekker_count }}+</b><span>Trekkers taken out since 2021</span></div>
      <div class="stat"><b>15</b><span>Maximum batch size</span></div>
      <div class="stat"><b>2</b><span>Guides on every departure</span></div>
    </div>
  </div>
  <a href="#how" class="hero-scroll">Scroll</a>
</section>

<section class="section section--tight section--surface">
  <div class="shell">
    <div class="head" style="max-width:none;margin-bottom:26px">
      <p class="kicker">Start here</p>
      <h2>Booking a trek takes four steps</h2>
      <p class="lede" style="margin-top:12px">
        Everything happens on this site. No phone calls, no deposit over UPI to a stranger, no
        WhatsApp group you have to join before you know the price.
      </p>
    </div>
    <div class="steps">
      <div class="step">
        <h3>Pick a trail</h3>
        <p>Each trek page lists the real distance, the maximum altitude, where the walk starts and
          where it ends, and an hour-by-hour plan for the day. Read the grade before the price.</p>
      </div>
      <div class="step">
        <h3>Choose a weekend</h3>
        <p>Pick a departure date and the number of trekkers in your group. Slots are checked against
          that trail's permit quota before the booking is confirmed.</p>
      </div>
      <div class="step">
        <h3>Pay online</h3>
        <p>Card or UPI. The price on the page is the price you pay, including GST, the booking fee,
          forest permits and gate fees. Nothing is collected at the trailhead.</p>
      </div>
      <div class="step">
        <h3>Get your brief</h3>
        <p>A receipt arrives immediately. Two days before departure you get the pickup point, the
          reporting time, your guide's number and a packing list for that specific trail.</p>
      </div>
    </div>
  </div>
</section>

<section class="section">
  <div class="shell">
    <div class="head row row--between" style="max-width:none;align-items:flex-end">
      <div>
        <p class="kicker">This season</p>
        <h2>TREKS</h2>
        <p class="lede" style="margin-top:12px">
          Saturday and Sunday departures, each with a lead guide and a sweep guide.
        </p>
      </div>
      <a href="/treks" class="btn btn--ghost btn--sm">See all {{ trek_count }} treks</a>
    </div>

    <div class="grid g-3">
      {% for trek in featured %}{% include "_trek_card.html" %}{% endfor %}
    </div>
  </div>
</section>

<section class="section" id="how">
  <div class="shell">
    <div class="head">
      <p class="kicker">How we operate</p>
      <h2>Small groups and accurate grading</h2>
      <p class="lede" style="margin-top:12px">
        Batches are capped, trails are graded from a recent walk, and permits are arranged in advance.
      </p>
    </div>
    <div class="grid g-4">
      <div class="card">
        <h3>Graded honestly</h3>
        <p class="small" style="margin-top:10px">Every trail is re-walked at the start of a season, and the
          grade comes from that walk, not a brochure. Savandurga is marked difficult because the granite is
          loose and exposed in three sections; if monsoon damage or a landslide changes a route, the grade is
          updated before the next batch goes out, not after someone gets caught out by it.</p>
      </div>
      <div class="card">
        <h3>Capped group size</h3>
        <p class="small" style="margin-top:10px">Between six and fifteen trekkers per batch, with a lead
          guide at the front and a sweep guide at the back regardless of group size — never just one guide.
          Both carry a first-aid kit and a whistle, and headcounts are taken at every rest point and trail
          junction, not only at the start and the end.</p>
      </div>
      <div class="card">
        <h3>Permits sorted</h3>
        <p class="small" style="margin-top:10px">Kudremukh and Kumara Parvatha sit inside reserve forest, so
          entries need a forest department permit and a capped daily quota, arranged in advance using the ID
          details from your booking. Savandurga and Skandagiri need only a gate fee, paid at the base. Either
          way, it's in the price you see — nothing extra to queue for or pay at the checkpost.</p>
      </div>
      <div class="card">
        <h3>Leave no trace</h3>
        <p class="small" style="margin-top:10px">Every trekker gets a waste bag at the base, and it's checked
          at the end, not just handed out — wrappers, peels and everything else that went up comes back down.
          No cooking fires or single-use plastic on any of our routes, and rest stops are chosen away from
          water sources so run-off stays clean for whoever's downstream.</p>
      </div>
    </div>
  </div>
</section>

<section class="section" id="grades">
  <div class="shell">
    <div class="head">
      <p class="kicker">Grading</p>
      <h2>What easy, moderate and difficult mean here</h2>
      <p class="lede" style="margin-top:12px">
        A grade is about the terrain and the exposure, not only the distance. A short trek can be
        graded difficult, and a long one can be fine for a first-timer.
      </p>
    </div>
    <div class="grid g-3">
      <div class="card">
        <h3>Easy</h3>
        <p class="small" style="margin-top:10px">Under 6 km, a marked path the whole way, and no section
          where a slip matters. If you can walk for two hours without stopping, you can do these. Nandi
          Hills and the shorter sunrise walks sit here. Good for a first trek, for children over ten,
          and for anyone coming back after a long gap.</p>
        <div class="row" style="margin-top:18px">
          <span class="pill">2 to 4 hours</span><span class="pill pill--muted">No scrambling</span>
        </div>
      </div>
      <div class="card">
        <h3>Moderate</h3>
        <p class="small" style="margin-top:10px">6 to 12 km with a continuous climb, some loose rock and
          a few short stretches where you use your hands. Skandagiri and Kodachadri are here. You want
          shoes with real grip and the ability to keep walking uphill for three hours. Most of our
          trekkers book this grade.</p>
        <div class="row" style="margin-top:18px">
          <span class="pill">4 to 7 hours</span><span class="pill pill--muted">Some exposure</span>
        </div>
      </div>
      <div class="card">
        <h3>Difficult</h3>
        <p class="small" style="margin-top:10px">Long days, sustained steep ground, exposed rock and no
          quick way down once you are committed. Savandurga and Kumara Parvatha are graded this way.
          You need prior trekking experience and honest fitness. We will say no at the briefing if the
          group is not ready for it.</p>
        <div class="row" style="margin-top:18px">
          <span class="pill">7 to 12 hours</span><span class="pill pill--muted">Experience needed</span>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="section section--surface">
  <div class="shell">
    <div class="pair">
      <div>
        <p class="kicker">What you get</p>
        <h2 style="margin-bottom:18px">Included in every price on this site</h2>
        <ul class="ticklist">
          <li>A lead guide at the front and a sweep guide at the back, on every single departure</li>
          <li>Forest department permits where the trail needs one, and gate fees where it does not</li>
          <li>Transport from the Bengaluru pickup point to the base and back, on the trails we run that way</li>
          <li>Breakfast or a packed meal, and drinking water refills at the planned stops</li>
          <li>A first-aid kit with both guides, and a route plan left with our office before you set off</li>
          <li>GST, the booking fee and your receipt, with nothing collected at the trailhead</li>
        </ul>
      </div>
      <div>
      <br><br>
        <p class="kicker">What to bring</p>
        <h2 style="margin-bottom:18px">Carried by you</h2>
        <ul class="ticklist no">
          <li>Shoes with a real grip sole. Running shoes are the single most common reason someone turns back</li>
          <li>Two litres of water minimum, three on the exposed granite trails in summer</li>
          <li>A headtorch for the night starts, with the batteries checked before you leave home</li>
          <li>A windproof layer. The top is always colder than the base, even in March</li>
          <li>A government photo ID, which is required at every forest checkpost</li>
          <li>Personal medication, and a word to your guide at the briefing about anything relevant</li>
        </ul>
        
      </div>
    </div>
  </div>
</section>

<section class="section">
  <div class="shell">
    <div class="head">
      <p class="kicker">Planning</p>
      <h2>Choosing a season</h2>
      <p class="lede" style="margin-top:12px">
        The same hill is a different trek in July and in January. If your dates are flexible, this is
        the part worth reading before you pick a weekend.
      </p>
    </div>
    <div class="season">
      <div><h4>June to September</h4><p>Peak monsoon. Streams run hard, leeches are everywhere and visibility
        drops to nothing. Most high trails stay shut.</p></div>
      <div><h4>October to November</h4><p>The best window. Grasslands are green, skies clear after the rain,
        and the whole ridge line is visible from the top.</p></div>
      <div><h4>December to February</h4><p>Cold mornings, dry trails, long views. Ideal for first-timers and
        for the longer Kumara Parvatha climb.</p></div>
      <div><h4>March to May</h4><p>Hot and exposed. Start before sunrise, carry more water than you think,
        and stick to the shorter rock climbs.</p></div>
    </div>
  </div>
</section>

<section class="section">
  <div class="shell">
    <div class="head">
      <p class="kicker">Reviews</p>
      <h2>From recent departures</h2>
    </div>
    <div class="grid g-3">
      <div class="quote">
        <p>First trek of my life and I never once felt like the slowest person there. The sweep guide
          stayed with our group the whole way up.</p>
        <div class="who"><span class="avatar">AR</span><div><b>Ananya R.</b><span>Skandagiri, November</span></div></div>
      </div>
      <div class="quote">
        <p>Kumara Parvatha nearly finished me, and the briefing told me it would. Glad they did not
          sugarcoat it. Bhattara Mane food was the highlight.</p>
        <div class="who"><span class="avatar">VK</span><div><b>Vikram K.</b><span>Kumara Parvatha, December</span></div></div>
      </div>
      <div class="quote">
        <p>Booked on a Thursday, on the rock by Saturday morning. Receipt, pickup point and packing
          list all arrived without me chasing anyone.</p>
        <div class="who"><span class="avatar">SM</span><div><b>Sneha M.</b><span>Savandurga, January</span></div></div>
      </div>
    </div>
  </div>
</section>

<section class="section section--surface">
  <div class="shell">
    <div class="head">
      <p class="kicker">Before you book</p>
      <h2>The questions we get most</h2>
    </div>
    <div class="grid g-2">
      <div class="panel">
        <h4 style="margin-bottom:10px">I have never trekked before. Where do I start?</h4>
        <p class="small">An easy or moderate grade, and ideally a trek with a daylight start. Skandagiri
          is a night climb, which is beautiful but is not the gentlest first outing. Tell us at booking
          and we will say plainly whether the trail you picked is the right one.</p>
      </div>
      <div class="panel">
        <h4 style="margin-bottom:10px">Can I change my date?</h4>
        <p class="small">Yes, up to 72 hours before departure, subject to a slot being free on the new
          date. Write to us from the email you booked with and mention the booking reference on your
          receipt.</p>
      </div>
      <div class="panel">
        <h4 style="margin-bottom:10px">What happens if the weather turns?</h4>
        <p class="small">We call it the evening before and tell everyone in the batch at the same time.
          If we cancel a departure, you choose between a full refund and a free move to another date.
          A guide can also stop a group mid-trail, and that call is final.</p>
      </div>
      <div class="panel">
        <h4 style="margin-bottom:10px">Is it safe to trek solo with you?</h4>
        <p class="small">Most people who book do it alone. You are in a batch of six to fifteen with two
          guides, and headcounts are taken at every rest point and trail junction rather than only at
          the start and the finish.</p>
      </div>
      <div class="panel">
        <h4 style="margin-bottom:10px">Are there age limits?</h4>
        <p class="small">Ten and above for easy trails with an adult, sixteen and above for the difficult
          grades. There is no upper limit. What matters is being able to walk uphill for the number of
          hours listed on the trek page.</p>
      </div>
      <div class="panel">
        <h4 style="margin-bottom:10px">Do you take group or private bookings?</h4>
        <p class="small">Ten or more trekkers, or a private batch on a date of your choosing, is quoted
          separately. Mention it on the contact form and we will come back with dates and a price.</p>
      </div>
    </div>
  </div>
</section>

<section class="cta">
  <h2>Book a weekend departure</h2>
  <p>Pick a trail, pick a weekend, and we will handle the permits, the transport and the guiding.</p>
  <a href="/treks" class="btn btn--primary" style="margin-top:20px">See available treks</a>
</section>
{% endblock %}
"""


TEMPLATES["_trek_card.html"] = """
<article class="trek-card">
  <a href="/trek/{{ trek.slug }}" class="shot">
    <img src="{{ trek.image_url }}" alt="{{ trek.name }}"
         onerror="this.onerror=null;this.src='{{ trek.fallback_image }}'">
    <span class="tags">
      <span class="pill">{{ trek.difficulty_band }}</span>
      <span class="pill pill--muted">{{ trek.rating }} rating</span>
    </span>
  </a>
  <div class="body">
    <div class="where">{{ trek.location }}</div>
    <h3>{{ trek.name }}</h3>
    <p class="desc">{{ trek.tagline }}</p>
    <div class="specs">
      <div><span>Time</span><b>{{ trek.duration }}</b></div>
      <div><span>Distance</span><b>{{ trek.distance }}</b></div>
      <div><span>Height</span><b>{{ trek.altitude }}</b></div>
    </div>
    <div class="row row--between card-foot">
      <div><span class="price">&#8377;{{ trek.price }}</span> <sub class="small">per person</sub></div>
      <a href="/trek/{{ trek.slug }}" class="btn btn--outline btn--sm">View trek</a>
    </div>
  </div>
</article>
"""


TEMPLATES["treks.html"] = """
{% extends "base.html" %}
{% block title %}All treks — PEAK{% endblock %}

{% block extra_css %}
.page-head{position:relative;overflow:hidden;padding:clamp(52px,6.5vw,88px) 0 clamp(34px,4vw,50px);
  border-bottom:1px solid var(--line);background:var(--surface-2)}
.page-head::before{content:"";position:absolute;inset:-60% 55% auto -10%;height:140%;pointer-events:none;
  background:radial-gradient(circle,rgba(255,255,255,.06),transparent 62%)}
.page-head .shell{position:relative;z-index:1}
.filters{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,1.3fr) auto;gap:18px;align-items:end;
  margin-top:34px;width:100%;
  background:rgba(255,255,255,.03);border:1px solid var(--line);border-radius:var(--r-xl);
  padding:clamp(18px,1.8vw,26px);box-shadow:var(--shadow-sm)}
.filters .field{margin:0}
.filters .btn{height:52px}
@media (max-width:760px){.filters{grid-template-columns:1fr 1fr}.filters .field:first-child{grid-column:1/-1}
  .filters .btn{grid-column:1/-1}}
.result-bar{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;
  margin-bottom:30px;padding-bottom:18px;border-bottom:1px solid var(--line)}
{% endblock %}

{% block body %}
<section class="page-head">
  <div class="shell">
    <p class="kicker">{{ total }} trails, all within a day of Bengaluru</p>
    <h1>All treks</h1>
    <form method="GET" action="/treks" class="filters">
      <div class="field">
        <label for="q">Search</label>
        <input id="q" type="search" name="q" value="{{ q }}" placeholder="Trail, hill or district">
      </div>
      <div class="field">
        <label for="sort">Sort by</label>
        <select id="sort" name="sort">
          <option value="" {{ 'selected' if not sort }}>Recommended</option>
          <option value="price" {{ 'selected' if sort == 'price' }}>Price, low to high</option>
          <option value="price_desc" {{ 'selected' if sort == 'price_desc' }}>Price, high to low</option>
          <option value="rating" {{ 'selected' if sort == 'rating' }}>Highest rated</option>
        </select>
      </div>
      <button class="btn btn--primary" type="submit">Apply</button>
    </form>
  </div>
</section>

<section class="section section--tight">
  <div class="shell">
    <div class="result-bar">
      <p class="small">Showing {{ treks|length }} of {{ total }} treks{% if q %} for &ldquo;{{ q }}&rdquo;{% endif %}</p>
      {% if q or sort %}<a href="/treks" class="btn btn--ghost btn--sm">Clear search</a>{% endif %}
    </div>

    {% if treks %}
      <div class="grid g-3">
        {% for trek in treks %}{% include "_trek_card.html" %}{% endfor %}
      </div>
    {% else %}
      <div class="empty card">
        <h2>No trails match that</h2>
        <p>Try a shorter search term, or a district such as Chikkamagaluru, Shivamogga or Ramanagara.</p>
        <a href="/treks" class="btn btn--primary">Show every trek</a>
      </div>
    {% endif %}
  </div>
</section>
{% endblock %}
"""


TEMPLATES["trek.html"] = """
{% extends "base.html" %}
{% block title %}{{ trek.name }} — PEAK{% endblock %}

{% block extra_css %}
/* ---------- detail hero: full-bleed, full photograph ---------- */
.t-hero{padding:0}
.t-wrap{position:relative;max-width:none;margin:0}
.t-frame{position:relative;overflow:hidden;border:0;border-bottom:1px solid var(--line);
  background:#05070a;aspect-ratio:21/9;min-height:clamp(400px,56vh,720px);max-height:88vh}
.t-frame .blur{position:absolute;inset:-8%;background-size:cover;background-position:center;
  filter:blur(46px) saturate(.85) brightness(.4);transform:scale(1.15)}
/* 4) The hero photo is now centred in its frame instead of being anchored
   low and to one side, and 9) it covers the frame edge to edge with no
   scale-up, so nothing drifts off to the left. */
.t-frame .shot{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;
  object-position:center center;transform:none}
.t-frame .scrim{position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(180deg,rgba(5,7,10,.66) 0%,rgba(5,7,10,.06) 26%,
                             rgba(5,7,10,.5) 58%,rgba(5,7,10,.95) 100%)}
.t-copy{position:absolute;left:0;right:0;bottom:0;z-index:2;padding:0 var(--pad) clamp(28px,3.6vw,64px)}
.t-copy .inner{max-width:var(--shell);margin:0 auto}
.t-copy h1{color:#fff;font-size:clamp(38px,5.6vw,84px);letter-spacing:-2.4px;font-weight:700;
  text-shadow:0 2px 34px rgba(0,0,0,.72)}
.t-copy .where{color:#fff;font-weight:700;font-size:12.5px;letter-spacing:2px;
  text-transform:uppercase;margin-bottom:10px}
.t-copy p{max-width:64ch;color:#dbe6ef;margin-top:14px;font-size:clamp(15px,1.15vw,18px);
  text-shadow:0 1px 14px rgba(0,0,0,.72)}
.t-copy .pill{background:rgba(9,13,19,.62);border-color:rgba(255,255,255,.26);color:#eaf1f8;
  backdrop-filter:blur(10px)}
.t-copy .row{margin-top:20px}
.crumbs{font-size:12.5px;color:#a9b8c6;margin-bottom:14px}
.crumbs a{color:#a9b8c6;text-decoration:none}
.crumbs a:hover{color:#fff}
@media (max-width:820px){
  .t-frame{aspect-ratio:4/3;min-height:0;max-height:none}
  .t-frame .scrim{background:linear-gradient(180deg,rgba(5,7,10,.3),rgba(5,7,10,.04))}
  .t-copy{position:static;padding:26px var(--pad) 0}
  .t-copy h1,.t-copy p{text-shadow:none}
  .t-copy .where{color:var(--text)}
  .t-copy p{color:var(--text-2)}
  .t-copy .pill{background:rgba(255,255,255,.05)}
}

/* ---------- 3) key facts: read as a list of points, one below the other,
   label on the left and value on the right, instead of a single wide
   strip of columns. 7) one white hairline around the box and between
   every point. ---------- */
.facts{display:block;background:var(--surface);
  border:1px solid var(--line);border-radius:var(--r-xl);overflow:hidden;
  margin-bottom:clamp(40px,4.6vw,64px);box-shadow:var(--shadow)}
.facts div{display:grid;grid-template-columns:230px minmax(0,1fr);align-items:baseline;
  gap:18px;padding:16px clamp(20px,2vw,30px);border-top:1px solid var(--line)}
.facts div:first-child{border-top:0}
.facts span{display:block;font-size:11px;letter-spacing:1.6px;text-transform:uppercase;
  color:var(--muted);font-weight:700}
.facts b{font-size:16px;font-weight:700;line-height:1.4;color:var(--text)}
@media (max-width:640px){
  .facts div{grid-template-columns:1fr;gap:4px;padding:15px 18px}
  .facts b{font-size:15px}
}

.layout{display:grid;grid-template-columns:minmax(0,1fr) 420px;gap:clamp(36px,4vw,68px);align-items:start}
@media (max-width:1060px){.layout{grid-template-columns:1fr}}
.block{margin-bottom:clamp(44px,5vw,70px)}
.block:last-child{margin-bottom:0}
.block h2{font-size:clamp(26px,2.4vw,36px);margin-bottom:10px}
.block > p.intro{color:var(--muted);margin-bottom:26px}
.prose p{color:var(--text-2);font-size:16px;line-height:1.85;margin-bottom:18px;max-width:72ch}
.day{display:grid;grid-template-columns:140px 1fr;gap:26px;padding:24px 0;border-top:1px solid var(--line)}
.day:last-child{border-bottom:1px solid var(--line)}
.day .when{font-family:var(--serif);font-size:16px;font-weight:700;color:var(--text)}
.day h4{font-family:var(--sans);font-size:15.5px;font-weight:700;margin-bottom:8px}
.day p{color:var(--text-2);font-size:15px;line-height:1.7}
@media (max-width:620px){.day{grid-template-columns:1fr;gap:6px}}
.two{display:grid;grid-template-columns:1fr 1fr;gap:var(--gap)}
@media (max-width:820px){.two{grid-template-columns:1fr}}
.pair{display:grid;grid-template-columns:1.05fr 1fr;gap:clamp(30px,3.4vw,58px);align-items:start}
/* 3) Once the two columns stack, the second heading would otherwise sit right
   under the last bullet of the first list. Give it real separation. */
@media (max-width:1000px){
  .pair{grid-template-columns:1fr}
  .pair > div + div{margin-top:clamp(26px,5vw,46px)}
}
.faq-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 clamp(32px,4vw,64px)}
@media (max-width:900px){.faq-grid{grid-template-columns:1fr}}
.panel--tall{height:100%}
.p-label{font-family:var(--sans);font-size:11.5px;letter-spacing:1.6px;text-transform:uppercase;
  font-weight:700;margin-bottom:14px;color:var(--text)}
.p-label--muted{color:var(--muted)}

/* ---------- photo carousel (detail page only) ---------- */
.carousel{position:relative;aspect-ratio:16/9;max-height:78vh;overflow:hidden;
  border-radius:var(--r-2xl);border:1px solid var(--line-strong);background:#05070a;box-shadow:var(--shadow-lg)}
.carousel .frames{position:absolute;inset:0}
.carousel .frames img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center center;
  opacity:0;transition:opacity .5s ease}
.carousel .frames img.on{opacity:1}
.carousel::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(180deg,rgba(5,7,10,.28),rgba(5,7,10,0) 30%,rgba(5,7,10,.4))}
.cbtn{position:absolute;top:50%;transform:translateY(-50%);z-index:3;
  width:clamp(48px,4vw,64px);height:clamp(48px,4vw,64px);border-radius:50%;cursor:pointer;
  display:grid;place-items:center;font-family:inherit;font-size:26px;line-height:1;
  color:var(--text);background:rgba(9,13,19,.62);border:1px solid rgba(255,255,255,.24);
  backdrop-filter:blur(12px);transition:background .18s,border-color .18s,color .18s,transform .18s}
.cbtn:hover{background:#fff;border-color:#fff;color:var(--brand-ink)}
.cbtn:active{transform:translateY(-50%) scale(.94)}
.cbtn.prev{left:clamp(14px,1.6vw,26px)}
.cbtn.next{right:clamp(14px,1.6vw,26px)}
.cdots{position:absolute;left:0;right:0;bottom:18px;z-index:3;display:flex;justify-content:center;gap:9px}
.cdots span{width:8px;height:8px;border-radius:50%;cursor:pointer;background:rgba(255,255,255,.34);
  transition:background .2s,transform .2s}
.cdots span.on{background:#fff;transform:scale(1.3)}
.ccount{position:absolute;right:clamp(14px,1.6vw,26px);top:clamp(14px,1.6vw,26px);z-index:3;
  padding:7px 14px;border-radius:var(--r-full);font-size:12.5px;font-weight:600;color:#eaf1f8;
  background:rgba(9,13,19,.62);border:1px solid rgba(255,255,255,.2);backdrop-filter:blur(10px)}
@media (max-width:640px){.carousel{aspect-ratio:4/3}}

details.faq{border-bottom:1px solid var(--line);padding:22px 0}
details.faq summary{cursor:pointer;font-weight:600;font-size:15.5px;list-style:none;display:flex;
  justify-content:space-between;gap:14px;color:var(--text)}
details.faq summary::-webkit-details-marker{display:none}
details.faq summary::after{content:"+";color:var(--text);font-size:20px;line-height:1}
details.faq[open] summary::after{content:"\\2013"}
details.faq p{color:var(--text-2);font-size:14.5px;margin-top:12px;max-width:66ch}

/* ---------- booking panel ---------- */
.booker{position:sticky;top:102px;
  background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,0)),var(--surface);
  border:1px solid var(--line-strong);border-radius:var(--r-2xl);padding:32px;box-shadow:var(--shadow-lg)}
.booker .top{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;
  padding-bottom:22px;margin-bottom:24px;border-bottom:1px solid var(--line)}
.booker .price{font-size:34px}
.booker label.lbl{display:block;font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;
  color:var(--muted);margin-bottom:12px}
.dates{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px}
.dates input{position:absolute;opacity:0;width:0;height:0}
.dates label{display:block}
.dates span{display:block;padding:12px 16px;border:1px solid var(--line-strong);border-radius:var(--r-sm);
  background:var(--surface-2);font-size:13.5px;font-weight:600;color:var(--text-2);cursor:pointer;transition:.15s}
.dates span:hover{border-color:#fff;color:#fff}
.dates input:checked + span{border-color:#fff;background:#fff;color:var(--brand-ink);font-weight:800;
  box-shadow:0 8px 22px rgba(0,0,0,.45)}
.dates input:focus-visible + span{outline:2px solid #fff;outline-offset:2px}
.stepper{display:flex;align-items:center;gap:0;border:1px solid var(--line-strong);border-radius:var(--r-sm);
  width:fit-content;overflow:hidden}
.stepper button{width:48px;height:48px;background:var(--fill);border:0;color:var(--text);font-size:19px;
  cursor:pointer;font-family:inherit;transition:background .15s,color .15s}
.stepper button:hover{background:rgba(255,255,255,.12);color:#fff}
.stepper input{width:66px;height:48px;text-align:center;background:var(--surface-2);border:0;
  border-left:1px solid var(--line-strong);border-right:1px solid var(--line-strong);
  color:var(--text);font-family:inherit;font-size:16px;font-weight:700}
.note{font-size:12px;color:var(--muted);margin-top:14px;text-align:center}
{% endblock %}

{% block body %}
{% set shots = trek.gallery_list() %}
{% set hero_photo = shots[0] if shots else trek.image_url %}

<section class="t-hero">
  <div class="t-wrap">
    <div class="t-frame">
      <div class="blur" style="background-image:url('{{ hero_photo }}'),url('{{ trek.fallback_image }}')"></div>
      <img class="shot" src="{{ hero_photo }}" alt="{{ trek.name }}" style="object-position:{{ hero_focus }}"
           onerror="this.onerror=null;this.src='{{ trek.fallback_image }}'">
      <div class="scrim"></div>
    </div>
    <div class="t-copy">
      <div class="inner">
        <div class="crumbs"><a href="/">Home</a> / <a href="/treks">Treks</a> / {{ trek.name }}</div>
        <div class="where">{{ trek.location }}</div>
        <h1>{{ trek.name }}</h1>
        <p>{{ trek.tagline }}</p>
        <div class="row">
          <span class="pill">{{ trek.difficulty_band }}</span>
          <span class="pill">{{ trek.duration }}</span>
          <span class="pill">{{ trek.rating }} from {{ trek.reviews_count }} trekkers</span>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="section section--tight">
  <div class="shell">
    <div class="facts">
      <div><span>Difficulty</span><b>{{ trek.difficulty }}</b></div>
      <div><span>Duration</span><b>{{ trek.duration }}</b></div>
      <div><span>Distance</span><b>{{ trek.distance }}</b></div>
      <div><span>Max altitude</span><b>{{ trek.altitude }}</b></div>
      <div><span>Group size</span><b>{{ trek.group_size }}</b></div>
      <div><span>Best season</span><b>{{ trek.best_season }}</b></div>
      <div><span>Starts at</span><b>{{ trek.starting_point }}</b></div>
      <div><span>Ends at</span><b>{{ trek.ending_point }}</b></div>
    </div>

    <div class="layout">
      <div>
        <div class="block">
          <h2>About this trail</h2>
          <div class="prose">
            <p>{{ trek.description }}</p>
            {% for para in trek.long_description.split('||') %}<p>{{ para.strip() }}</p>{% endfor %}
          </div>
        </div>

        {% if trek.itinerary_list() %}
        <div class="block">
          <h2>The plan</h2>
          <p class="intro">Indicative timings. These shift with the season and the weather.</p>
          {% for step in trek.itinerary_list() %}
          <div class="day">
            <div class="when">{{ step.when }}</div>
            <div><h4>{{ step.title }}</h4><p>{{ step.text }}</p></div>
          </div>
          {% endfor %}
        </div>
        {% endif %}
      </div>

      <aside>
        <form class="booker" method="POST" action="/cart/add">
          <input type="hidden" name="trek_id" value="{{ trek.id }}">
          <div class="top">
            <div>
              <span class="price">&#8377;{{ trek.price }}</span>
              <div class="small">per person, all inclusive</div>
            </div>
            <span class="pill pill--ok">Booking open</span>
          </div>

          <label class="lbl">Choose a date</label>
          <div class="dates">
            {% for d in available_dates %}
            <label>
              <input type="radio" name="trek_date" value="{{ d }}" {{ 'checked' if loop.first }} required>
              <span>{{ d|pretty_date }}</span>
            </label>
            {% endfor %}
          </div>

          <label class="lbl">Trekkers</label>
          <div class="stepper">
            <button type="button" onclick="bump(-1)" aria-label="One fewer">&minus;</button>
            <input type="number" id="people" name="people" value="1" min="1" max="20" onchange="recalc()">
            <button type="button" onclick="bump(1)" aria-label="One more">+</button>
          </div>

          <hr class="divider" style="margin:22px 0">
          <div class="line"><span>Trek fee</span><b id="lineTotal">&#8377;{{ trek.price }}</b></div>
          <div class="line"><span>GST and booking fee</span><b>Added at checkout</b></div>

          <button class="btn btn--primary btn--wide" type="submit" style="margin-top:14px">Add to cart</button>
          <p class="note">Free cancellation and date changes up to 72 hours before departure.</p>
        </form>
      </aside>
    </div>
  </div>
</section>

{% set carousel_shots = shots[1:] if shots|length > 1 else shots %}
{% if carousel_shots %}
<section class="section section--tight" style="padding-top:0">
  <div class="shell">
    <div class="carousel" id="gal">
      <div class="frames">
        {% for src in carousel_shots %}
        <img class="{{ 'on' if loop.first }}" src="{{ src }}" alt="{{ trek.name }}"
             {{ 'loading=lazy' if not loop.first }}
             onerror="this.onerror=null;this.src='{{ trek.fallback_image }}'">
        {% endfor %}
      </div>
      {% if carousel_shots|length > 1 %}
      <span class="ccount"><b id="galNow">1</b> / {{ carousel_shots|length }}</span>
      <button class="cbtn prev" type="button" onclick="galNav(-1)" aria-label="Previous photograph">&#8249;</button>
      <button class="cbtn next" type="button" onclick="galNav(1)" aria-label="Next photograph">&#8250;</button>
      <div class="cdots">
        {% for src in carousel_shots %}<span class="{{ 'on' if loop.first }}" onclick="galGo({{ loop.index0 }})"></span>{% endfor %}
      </div>
      {% endif %}
    </div>
  </div>
</section>
{% endif %}

<section class="section section--surface">
  <div class="shell">
    <div class="block">
      <h2>What the price covers</h2>
      <div class="two" style="margin-top:22px">
        <div class="panel panel--tall">
          <h4 class="p-label">Included</h4>
          <ul class="ticklist">{% for i in trek.inclusion_list() %}<li>{{ i }}</li>{% endfor %}</ul>
        </div>
        <div class="panel panel--tall">
          <h4 class="p-label p-label--muted">Not included</h4>
          <ul class="ticklist no">{% for i in trek.exclusion_list() %}<li>{{ i }}</li>{% endfor %}</ul>
        </div>
      </div>
    </div>

    <div class="block">
      <h2>Highlights and kit</h2>
      <div class="two" style="margin-top:22px">
        <div class="panel panel--tall">
          <h4 class="p-label">Worth the climb</h4>
          <ul class="ticklist">{% for i in trek.highlight_list() %}<li>{{ i }}</li>{% endfor %}</ul>
        </div>
        <div class="panel panel--tall">
          <h4 class="p-label">Pack this</h4>
          <ul class="ticklist">{% for i in trek.carry_list() %}<li>{{ i }}</li>{% endfor %}</ul>
        </div>
      </div>
    </div>

    <div class="block">
      <div class="pair">
        <div>
          <h2>Getting there</h2>
          <div class="prose" style="margin-top:18px"><p>{{ trek.how_to_reach }}</p></div>
        </div>
        <div>
          <h2>Safety and permits</h2>
          <div class="two" style="margin-top:18px">
            <div class="panel panel--tall">
              <h4 class="p-label">On the trail</h4>
              <p class="small">{{ trek.safety_info }}</p>
            </div>
            <div class="panel panel--tall">
              <h4 class="p-label">Permits</h4>
              <p class="small">{{ trek.permit_info }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    {% if trek.faq_list() %}
    <div class="block">
      <h2>Common questions</h2>
      <div class="faq-grid" style="margin-top:14px">
      {% for f in trek.faq_list() %}
        <details class="faq"><summary>{{ f.q }}</summary><p>{{ f.a }}</p></details>
      {% endfor %}
      </div>
    </div>
    {% endif %}
  </div>
</section>

{% if related %}
<section class="section">
  <div class="shell">
    <div class="head"><p class="kicker">Also worth your weekend</p><h2>Other trails near here</h2></div>
    <div class="grid g-3">{% for trek in related %}{% include "_trek_card.html" %}{% endfor %}</div>
  </div>
</section>
{% endif %}
{% endblock %}

{% block extra_js %}
<script>
var UNIT = {{ trek.price }};
function recalc(){
  var el = document.getElementById('people');
  var n = parseInt(el.value, 10);
  if(isNaN(n) || n < 1) n = 1;
  if(n > 20) n = 20;
  el.value = n;
  document.getElementById('lineTotal').textContent = '\\u20B9' + (UNIT * n);
}
function bump(step){
  var el = document.getElementById('people');
  el.value = (parseInt(el.value, 10) || 1) + step;
  recalc();
}
recalc();

/* ---- photo carousel: one image at a time, arrows and dots ---- */
var galSlides = document.querySelectorAll('#gal .frames img');
var galDots   = document.querySelectorAll('#gal .cdots span');
var galIndex  = 0;
function galGo(n){
  if(!galSlides.length) return;
  galIndex = (n % galSlides.length + galSlides.length) % galSlides.length;
  for(var i = 0; i < galSlides.length; i++){
    galSlides[i].classList.toggle('on', i === galIndex);
    if(galDots[i]) galDots[i].classList.toggle('on', i === galIndex);
  }
  var counter = document.getElementById('galNow');
  if(counter) counter.textContent = galIndex + 1;
}
function galNav(step){ galGo(galIndex + step); }
document.addEventListener('keydown', function(e){
  if(!galSlides.length) return;
  var t = e.target.tagName;
  if(t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT') return;
  if(e.key === 'ArrowLeft')  galNav(-1);
  if(e.key === 'ArrowRight') galNav(1);
});
</script>
{% endblock %}
"""


TEMPLATES["cart.html"] = """
{% extends "base.html" %}
{% block title %}Your cart — PEAK{% endblock %}

{% block extra_css %}
.cart-layout{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:clamp(32px,4vw,56px);align-items:start}
@media (max-width:940px){.cart-layout{grid-template-columns:1fr}}
.c-item{display:grid;grid-template-columns:170px minmax(0,1fr) auto;gap:26px;padding:24px;background:var(--surface);
  border:1px solid var(--line);border-radius:var(--r-xl);margin-bottom:20px;box-shadow:var(--shadow)}
.c-item img{width:170px;height:128px;object-fit:cover;border-radius:var(--r-md)}
.c-item h3{font-size:22px;margin-bottom:6px}
.c-item .meta{font-size:13.5px;color:var(--muted);line-height:1.6}
.c-right{text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:14px}
.qty{display:flex;align-items:center;gap:8px}
.qty input{width:64px;padding:9px;text-align:center;background:var(--surface-2);border:1px solid var(--line-strong);
  border-radius:var(--r-sm);color:var(--text);font-family:inherit;font-weight:600}
@media (max-width:820px){.c-item{grid-template-columns:1fr}.c-item img{width:100%;height:210px}
  .c-right{align-items:flex-start;text-align:left}}
.sum{position:sticky;top:102px;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-xl);padding:32px;box-shadow:var(--shadow-lg)}
.steps-bar{display:flex;gap:12px;align-items:center;font-size:13.5px;color:var(--muted);margin-bottom:32px;flex-wrap:wrap}
.steps-bar b{color:var(--text)}
{% endblock %}

{% block body %}
<section class="section section--tight">
  <div class="shell">
    <div class="steps-bar"><b>1. Cart</b><span>&rarr;</span><span>2. Checkout</span><span>&rarr;</span><span>3. Confirmation</span></div>
    <h1 style="margin-bottom:30px">Your cart</h1>

    {% if cart %}
    <div class="cart-layout">
      <div>
        {% for item in cart %}
        <div class="c-item">
          <img src="{{ item.image_url }}" alt="{{ item.trek_name }}" onerror="this.style.visibility='hidden'">
          <div>
            <h3>{{ item.trek_name }}</h3>
            <p class="meta">{{ item.location }}</p>
            <p class="meta" style="margin-top:6px">{{ item.trek_date|pretty_date }}</p>
            <p class="meta">&#8377;{{ item.price }} per person</p>
            <a href="/trek/{{ item.trek_slug }}" class="small" style="color:#fff;font-weight:600;text-decoration:none">View trek details</a>
          </div>
          <div class="c-right">
            <strong class="price">&#8377;{{ item.subtotal() }}</strong>
            <form method="POST" action="/cart/update/{{ item.id }}" class="qty">
              <input type="number" name="people" value="{{ item.people }}" min="1" max="20" aria-label="Trekkers">
              <button class="btn btn--ghost btn--sm" type="submit">Update</button>
            </form>
            <form method="POST" action="/cart/remove/{{ item.id }}">
              <button class="btn btn--danger" type="submit">Remove</button>
            </form>
          </div>
        </div>
        {% endfor %}
        <a href="/treks" class="btn btn--ghost btn--sm" style="margin-top:8px">Add another trek</a>
      </div>

      <aside class="sum">
        <h3 style="margin-bottom:18px">Summary</h3>
        <div class="line"><span>{{ cart_count }} trekker{{ '' if cart_count == 1 else 's' }}</span><b>&#8377;{{ subtotal }}</b></div>
        <div class="line"><span>GST at 5%</span><b>&#8377;{{ gst }}</b></div>
        <div class="line"><span>Booking fee</span><b>&#8377;{{ booking_fee }}</b></div>
        <div class="line line--total"><span>Total</span><b>&#8377;{{ total }}</b></div>
        <a href="/checkout" class="btn btn--primary btn--wide" style="margin-top:20px">Go to checkout</a>
        {% if not current_user %}
        <p class="small" style="margin-top:14px;text-align:center">You will be asked to sign in at checkout. Your cart is saved.</p>
        {% endif %}
      </aside>
    </div>
    {% else %}
      <div class="empty card">
        <h2>Nothing in your cart yet</h2>
        <p>Pick a trail and a weekend, and it will show up here.</p>
        <a href="/treks" class="btn btn--primary">Browse treks</a>
      </div>
    {% endif %}

    {% if current_user %}
      <hr class="divider" style="margin:56px 0 30px">
      <div class="row row--between" style="margin-bottom:18px">
        <h2 style="font-size:26px">Recent bookings</h2>
        <a href="/bookings" class="btn btn--ghost btn--sm">See all bookings</a>
      </div>
      {% if recent_orders %}
        {% for order in recent_orders %}
        <div class="panel" style="margin-bottom:14px">
          <div class="row row--between">
            <div>
              <b>{{ order.display_ref() }}</b>
              <p class="small">{{ order.created_at.strftime('%d %b %Y') }} &nbsp;|&nbsp; {{ order.headcount() }} trekker(s)</p>
            </div>
            <div class="row">
              <span class="pill pill--ok">{{ order.status }}</span>
              <a href="/order/{{ order.id }}/confirmation" class="btn btn--ghost btn--sm">Receipt</a>
            </div>
          </div>
        </div>
        {% endfor %}
      {% else %}
        <p class="small">No bookings yet. Your first one will appear here.</p>
      {% endif %}
    {% endif %}
  </div>
</section>
{% endblock %}
"""


TEMPLATES["checkout.html"] = """
{% extends "base.html" %}
{% block title %}Checkout — PEAK{% endblock %}

{% block extra_css %}
.co{display:grid;grid-template-columns:minmax(0,1fr) 400px;gap:clamp(34px,4vw,60px);align-items:start}
@media (max-width:940px){.co{grid-template-columns:1fr}}
.sum{position:sticky;top:102px;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-xl);padding:32px;box-shadow:var(--shadow-lg)}
.steps-bar{display:flex;gap:12px;align-items:center;font-size:13.5px;color:var(--muted);margin-bottom:32px;flex-wrap:wrap}
.steps-bar b{color:var(--text)}
.tabs{display:flex;gap:14px;margin-bottom:24px}
.tabs label{flex:1;text-align:center;padding:18px;border:1px solid var(--line-strong);border-radius:var(--r-md);
  background:var(--surface-2);font-size:14.5px;font-weight:600;color:var(--text-2);cursor:pointer;transition:.15s}
.tabs label:hover{border-color:#fff;color:#fff}
.tabs input{position:absolute;opacity:0;width:0;height:0}
.tabs label.on{border-color:#fff;color:var(--brand-ink);background:#fff;font-weight:800;
  box-shadow:0 10px 26px rgba(0,0,0,.45)}
.pay{display:none}
.pay.on{display:block}
.qr{text-align:center;padding:28px;background:var(--fill);border:1px solid var(--line);
  border-radius:var(--r-lg);margin-bottom:22px}
.qr img{width:190px;height:190px;margin:0 auto;border-radius:12px;background:#fff;padding:10px;border:1px solid var(--line)}
.qr p{font-size:12.5px;color:var(--muted);margin:12px auto 0;max-width:34ch}
.sandbox{border:1px solid var(--line);border-left:3px solid #fff;background:var(--surface);
  border-radius:var(--r-md);padding:18px 22px;font-size:13.5px;line-height:1.7;color:var(--text-2);
  margin-bottom:34px;max-width:900px;box-shadow:var(--shadow-sm)}
.sandbox b{color:#fff;font-weight:800}
{% endblock %}

{% block body %}
<section class="section section--tight">
  <div class="shell">
    <div class="steps-bar"><span>1. Cart</span><span>&rarr;</span><b>2. Checkout</b><span>&rarr;</span><span>3. Confirmation</span></div>
    <h1 style="margin-bottom:26px">Checkout</h1>

    <div class="sandbox">
      <b>Sandbox gateway.</b> No money moves. Card 4242 4242 4242 4242 is approved, 4000 0000 0000 0002 is declined.
      Any UPI ID like name@bank is approved, anything starting with fail is declined.
    </div>

    <div class="co">
      <form method="POST" action="/checkout" id="coForm">
        <h3 style="margin-bottom:16px">Who is trekking</h3>
        <div class="field-row">
          <div class="field"><label for="name">Full name</label>
            <input id="name" type="text" name="name" value="{{ form.name }}" required></div>
          <div class="field"><label for="phone">Mobile number</label>
            <input id="phone" type="tel" name="phone" value="{{ form.phone }}" placeholder="10 digits" required></div>
        </div>
        <div class="field"><label for="email">Email for the receipt</label>
          <input id="email" type="email" name="email" value="{{ form.email }}" required>
          <p class="hint">Your booking confirmation and trek brief go here.</p></div>

        <h3 style="margin:30px 0 16px">How you want to pay</h3>
        <div class="tabs">
          <label id="tabCard" class="{{ 'on' if selected_method == 'card' }}">
            <input type="radio" name="payment_method" value="card" {{ 'checked' if selected_method == 'card' }} onchange="pick('card')">Card</label>
          <label id="tabUpi" class="{{ 'on' if selected_method == 'upi' }}">
            <input type="radio" name="payment_method" value="upi" {{ 'checked' if selected_method == 'upi' }} onchange="pick('upi')">UPI</label>
        </div>

        <div class="pay {{ 'on' if selected_method == 'card' }}" id="payCard">
          <div class="field"><label for="card_number">Card number</label>
            <input id="card_number" type="text" name="card_number" placeholder="4242 4242 4242 4242" maxlength="19" inputmode="numeric"></div>
          <div class="field-row">
            <div class="field"><label for="expiry">Expiry</label>
              <input id="expiry" type="text" name="expiry" placeholder="12/28" maxlength="5"></div>
            <div class="field"><label for="cvv">CVV</label>
              <input id="cvv" type="text" name="cvv" placeholder="123" maxlength="4" inputmode="numeric"></div>
          </div>
        </div>

        <div class="pay {{ 'on' if selected_method == 'upi' }}" id="payUpi">
          <div class="qr">
            <img src="{{ qr_data_uri }}" alt="UPI QR code">
            <p>Scan to pay &#8377;{{ total }}. Demo QR only, nothing is charged.</p>
          </div>
          <div class="field"><label for="upi_id">UPI ID</label>
            <input id="upi_id" type="text" name="upi_id" placeholder="yourname@bank"></div>
        </div>

        <button class="btn btn--primary btn--wide" type="submit" style="margin-top:10px">Pay &#8377;{{ total }} and confirm</button>
        <p class="small" style="text-align:center;margin-top:12px">Free cancellation up to 72 hours before the trek date.</p>
      </form>

      <aside class="sum">
        <h3 style="margin-bottom:18px">Order summary</h3>
        {% for item in cart %}
        <div class="line">
          <span>{{ item.trek_name }}<br><span class="small">{{ item.trek_date|pretty_date }} &nbsp;|&nbsp; {{ item.people }}x</span></span>
          <b>&#8377;{{ item.subtotal() }}</b>
        </div>
        {% endfor %}
        <hr class="divider" style="margin:18px 0">
        <div class="line"><span>Subtotal</span><b>&#8377;{{ subtotal }}</b></div>
        <div class="line"><span>GST at 5%</span><b>&#8377;{{ gst }}</b></div>
        <div class="line"><span>Booking fee</span><b>&#8377;{{ booking_fee }}</b></div>
        <div class="line line--total"><span>Total</span><b>&#8377;{{ total }}</b></div>
        <a href="/cart" class="btn btn--ghost btn--wide btn--sm" style="margin-top:18px">Back to cart</a>
      </aside>
    </div>
  </div>
</section>
{% endblock %}

{% block extra_js %}
<script>
function pick(m){
  var card = m === 'card';
  document.getElementById('payCard').classList.toggle('on', card);
  document.getElementById('payUpi').classList.toggle('on', !card);
  document.getElementById('tabCard').classList.toggle('on', card);
  document.getElementById('tabUpi').classList.toggle('on', !card);
  document.getElementById('card_number').required = card;
  document.getElementById('expiry').required = card;
  document.getElementById('cvv').required = card;
  document.getElementById('upi_id').required = !card;
}
pick('{{ selected_method }}');
</script>
{% endblock %}
"""


TEMPLATES["confirmation.html"] = """
{% extends "base.html" %}
{% block title %}Booking {{ order.order_ref }} — PEAK{% endblock %}

{% block extra_css %}
.done{text-align:center;max-width:640px;margin:0 auto clamp(40px,5vw,60px)}
.done .lede{margin-left:auto;margin-right:auto}
.mark{width:84px;height:84px;margin:0 auto 26px;border-radius:50%;display:grid;place-items:center;font-size:36px}
.mark.ok{background:rgba(255,255,255,.16);border:1px solid #fff;color:#fff;font-weight:800;
  box-shadow:0 0 44px rgba(255,255,255,.14)}
.mark.no{background:transparent;border:1px solid var(--line);color:var(--muted);font-weight:600}
.steps-bar{display:flex;gap:12px;align-items:center;justify-content:center;font-size:13.5px;color:var(--muted);
  margin-bottom:40px;flex-wrap:wrap}
.steps-bar b{color:var(--text)}
.ticket{display:grid;grid-template-columns:140px minmax(0,1fr) auto;gap:24px;align-items:center;
  padding:22px 0;border-bottom:1px solid var(--line)}
.ticket img{width:140px;height:100px;object-fit:cover;border-radius:var(--r-md)}
.ticket b{font-size:17px}
@media (max-width:680px){.ticket{grid-template-columns:1fr}.ticket img{width:100%;height:190px}}
.next li{margin-bottom:14px}
{% endblock %}

{% block body %}
<section class="section section--tight">
  <div class="shell shell--narrow">
    <div class="steps-bar"><span>1. Cart</span><span>&rarr;</span><span>2. Checkout</span><span>&rarr;</span><b>3. Confirmation</b></div>

    <div class="done">
      {% if paid %}
        <div class="mark ok">&#10003;</div>
        <h1>Booking confirmed</h1>
        <p class="lede" style="margin:12px auto 0">
          Reference <b style="color:var(--text)">{{ order.order_ref }}</b>. A receipt with the full
          breakdown has been sent to {{ order.email }}.
        </p>
      {% else %}
        <div class="mark no">!</div>
        <h1>Payment not completed</h1>
        <p class="lede" style="margin:12px auto 0">
          Reference {{ order.order_ref }} is saved as unpaid and no slot is held. Your cart is unchanged,
          so you can retry the payment.
        </p>
      {% endif %}
    </div>

    <div class="card" style="margin-bottom:20px">
      <h3 style="margin-bottom:18px">Booking details</h3>
      <div class="line"><span>Reference</span><b>{{ order.order_ref }}</b></div>
      <div class="line"><span>Booked on</span><b>{{ order.created_at.strftime('%d %b %Y, %I:%M %p') }}</b></div>
      <div class="line"><span>Paid with</span><b>{{ payment.method }}{% if payment.upi_id %} ({{ payment.upi_id }}){% endif %}</b></div>
      <div class="line"><span>Payment status</span>
        <span class="pill {{ 'pill--ok' if paid else 'pill--bad' }}">{{ payment.status }}</span></div>
      <div class="line"><span>Transaction ID</span><b>{{ payment.transaction_id }}</b></div>
      <div class="line"><span>Contact</span><b>{{ order.phone }}</b></div>
    </div>

    <div class="card" style="margin-bottom:20px">
      <h3 style="margin-bottom:12px">Your treks</h3>
      {% for item in order.items() %}
      <div class="ticket">
        <img src="{{ item.image_url }}" alt="{{ item.trek_name }}" onerror="this.style.visibility='hidden'">
        <div>
          <b>{{ item.trek_name }}</b>
          <p class="small">{{ item.location }}</p>
          <p class="small">{{ item.trek_date|pretty_date }} &nbsp;|&nbsp; {{ item.people }} trekker{{ '' if item.people == 1 else 's' }}</p>
        </div>
        <b class="price" style="font-size:18px">&#8377;{{ item.subtotal() }}</b>
      </div>
      {% endfor %}
      <div style="margin-top:18px">
        <div class="line"><span>Subtotal</span><b>&#8377;{{ order.subtotal }}</b></div>
        <div class="line"><span>GST at 5%</span><b>&#8377;{{ order.gst }}</b></div>
        <div class="line"><span>Booking fee</span><b>&#8377;{{ order.booking_fee }}</b></div>
        <div class="line line--total"><span>{{ 'Total paid' if paid else 'Amount due' }}</span><b>&#8377;{{ order.total }}</b></div>
      </div>
    </div>

    {% if paid %}
    <div class="card" style="margin-bottom:26px">
      <h3 style="margin-bottom:14px">What happens next</h3>
      <ul class="ticklist next">
        <li>A receipt with this reference is in your inbox.</li>
        <li>Your pre-trek brief is emailed two days before departure.</li>
        <li>Arrive 30 minutes before the listed start time; forest checkposts verify photo ID.</li>
        <li>Date changes and cancellations are free up to 72 hours before departure.</li>
      </ul>
    </div>
    {% endif %}

    <div class="row">
      {% if paid %}
        <a href="/bookings" class="btn btn--primary">See all my bookings</a>
        <a href="/treks" class="btn btn--ghost">Book another trek</a>
      {% else %}
        <a href="/checkout" class="btn btn--primary">Try payment again</a>
        <a href="/cart" class="btn btn--ghost">Back to cart</a>
      {% endif %}
    </div>
  </div>
</section>
{% endblock %}
"""


TEMPLATES["bookings.html"] = """
{% extends "base.html" %}
{% block title %}My bookings — PEAK{% endblock %}

{% block extra_css %}
.b-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-xl);padding:32px;
  margin-bottom:20px;box-shadow:var(--shadow)}
.b-top{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:flex-start;margin-bottom:22px;
  padding-bottom:22px;border-bottom:1px solid var(--line)}
.b-ref{font-family:var(--serif);font-size:23px;letter-spacing:-.5px}
.tally{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1px;background:var(--line);
  border:1px solid var(--line);border-radius:var(--r-xl);overflow:hidden;
  margin-bottom:clamp(40px,5vw,60px);box-shadow:var(--shadow)}
.tally div{background:var(--surface);padding:28px}
.tally span{display:block;font-size:12.5px;color:var(--muted);margin-bottom:4px}
.tally b{font-family:var(--serif);font-size:34px;letter-spacing:-1px}
{% endblock %}

{% block body %}
<section class="section section--tight">
  <div class="shell">
    <h1 style="margin-bottom:10px">My bookings</h1>
    <p class="lede" style="margin-bottom:34px">Every trek you have booked, paid for or attempted, newest first.</p>

    <div class="tally">
      <div><span>Confirmed treks</span><b>{{ stats.paid }}</b></div>
      <div><span>Trekkers booked</span><b>{{ stats.people }}</b></div>
      <div><span>Total spent</span><b>&#8377;{{ stats.spent }}</b></div>
      <div><span>Unfinished payments</span><b>{{ stats.failed }}</b></div>
    </div>

    {% if orders %}
      {% for order in orders %}
      <div class="b-card">
        <div class="b-top">
          <div>
            <div class="b-ref">{{ order.order_ref }}</div>
            <p class="small">Booked {{ order.created_at.strftime('%d %b %Y, %I:%M %p') }}</p>
          </div>
          <div class="row">
            <span class="pill {{ 'pill--ok' if order.status == 'paid' else 'pill--bad' }}">{{ order.status }}</span>
            <a href="/order/{{ order.id }}/confirmation" class="btn btn--ghost btn--sm">View receipt</a>
          </div>
        </div>
        {% for item in order.items() %}
        <div class="line">
          <span><b style="color:var(--text)">{{ item.trek_name }}</b><br>
            <span class="small">{{ item.trek_date|pretty_date }} &nbsp;|&nbsp; {{ item.people }} trekker{{ '' if item.people == 1 else 's' }}</span></span>
          <b>&#8377;{{ item.subtotal() }}</b>
        </div>
        {% endfor %}
        <div class="line line--total"><span>{{ 'Paid' if order.status == 'paid' else 'Not paid' }}</span><b>&#8377;{{ order.total }}</b></div>
      </div>
      {% endfor %}
    {% else %}
      <div class="empty card">
        <h2>No bookings yet</h2>
        <p>Once you book a trail it will live here, with the receipt and the trek brief.</p>
        <a href="/treks" class="btn btn--primary">Browse treks</a>
      </div>
    {% endif %}
  </div>
</section>
{% endblock %}
"""


TEMPLATES["auth.html"] = """
{% extends "base.html" %}
{% block title %}{{ 'Create your account' if mode == 'signup' else 'Sign in' }} — PEAK{% endblock %}

{% block extra_css %}
.auth{display:grid;grid-template-columns:1fr 1fr;min-height:640px;background:var(--surface);
  border:1px solid var(--line);border-radius:var(--r-xl);overflow:hidden;
  margin:clamp(40px,6vw,86px) auto;max-width:1120px;box-shadow:var(--shadow-lg)}
/* 1) + 9) signin.jpg / signup.jpg, centred and covering the whole panel */
.auth .art{position:relative;background-color:var(--stone);background-position:center center;
  background-size:cover;background-repeat:no-repeat;display:flex;align-items:flex-end;padding:34px}
.auth .art::after{content:"";position:absolute;inset:0;
  background:linear-gradient(180deg,rgba(5,8,12,.25) 0%,rgba(5,8,12,.4) 40%,rgba(5,8,12,.92) 100%)}
.auth .art .say{position:relative;z-index:2}
.auth .art .say p{font-family:var(--serif);font-size:20px;line-height:1.4;color:#fff}
.auth .art .say span{font-size:12.5px;letter-spacing:1.6px;text-transform:uppercase;color:#fff}
.auth .side{padding:clamp(36px,4vw,62px)}
@media (max-width:860px){.auth{grid-template-columns:1fr;margin:24px auto;min-height:0}
  .auth .art{min-height:230px}.auth .side{padding:36px 26px}}
{% endblock %}

{% block body %}
<div class="shell">
  <div class="auth">
    <div class="art" style="background-image:url('{{ art }}'),url('{{ art_fallback }}')">
      
    </div>

    <div class="side">
      <p class="kicker">{{ 'New here' if mode == 'signup' else 'Welcome back' }}</p>
      <h1 style="font-size:36px;margin-bottom:10px">{{ 'Create your account' if mode == 'signup' else 'Sign in' }}</h1>
      <p class="small" style="margin-bottom:28px">
        {{ 'It takes a minute, and it keeps your bookings and receipts in one place.' if mode == 'signup'
           else 'Use the email you booked with.' }}
      </p>

      <form method="POST">
        <input type="hidden" name="next" value="{{ next_url }}">
        {% if mode == 'signup' %}
        <div class="field"><label for="name">Full name</label>
          <input id="name" type="text" name="name" value="{{ form.name }}" placeholder="As it should appear on the booking" required></div>
        <div class="field"><label for="phone">Mobile number</label>
          <input id="phone" type="tel" name="phone" value="{{ form.phone }}" placeholder="Optional, used on trek day"></div>
        {% endif %}

        <div class="field"><label for="email">Email</label>
          <input id="email" type="email" name="email" value="{{ form.email }}" placeholder="you@example.com" required></div>

        <div class="field"><label for="password">Password</label>
          <input id="password" type="password" name="password"
                 placeholder="{{ 'At least 6 characters' if mode == 'signup' else 'Your password' }}" required>
          {% if mode == 'signup' %}<p class="hint">Six characters minimum. Nothing clever required.</p>{% endif %}
        </div>

        <button class="btn btn--primary btn--wide" type="submit">
          {{ 'Create account' if mode == 'signup' else 'Sign in' }}
        </button>
      </form>

      <p class="small" style="text-align:center;margin-top:22px">
        {% if mode == 'signup' %}
          Already booked with us? <a href="/signin" style="color:#fff;text-decoration:underline;font-weight:700">Sign in</a>
        {% else %}
          First time here? <a href="/signup" style="color:#fff;text-decoration:underline;font-weight:700">Create an account</a>
        {% endif %}
      </p>
    </div>
  </div>
</div>
{% endblock %}
"""


TEMPLATES["about.html"] = """
{% extends "base.html" %}
{% block title %}About PEAK{% endblock %}

{% block extra_css %}
.about-hero{padding:clamp(66px,8vw,110px) 0 clamp(50px,6vw,80px);border-bottom:1px solid var(--line);background:var(--surface-2)}
.tally{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:1px;background:var(--line);
  border:1px solid var(--line);border-radius:var(--r-xl);overflow:hidden;margin-top:clamp(40px,5vw,60px)}
.tally div{background:var(--surface);padding:30px}
.tally b{display:block;font-family:var(--serif);font-size:36px;letter-spacing:-1px}
.tally span{font-size:13.5px;color:var(--muted)}
.prose p{color:var(--text-2);margin-bottom:16px;max-width:68ch}
.crew{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:var(--gap)}
.crew .who{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-xl);
  padding:32px;box-shadow:var(--shadow)}
.crew .avatar{width:54px;height:54px;font-size:16px;margin-bottom:20px}
.crew h3{font-size:21px;margin-bottom:6px}
.crew .who--lead{grid-column:1/-1;display:grid;grid-template-columns:auto minmax(0,1fr);
  gap:clamp(22px,2.4vw,34px);align-items:start}
.crew .who--lead .avatar{width:72px;height:72px;font-size:20px;margin-bottom:0}
@media (max-width:720px){.crew .who--lead{grid-template-columns:1fr}}
/* 1) Fixed three columns instead of auto-fit. Six rules over three columns
   is exactly two full rows, so the grid's own background can never show
   through as an empty grey cell at the end. */
.rules{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;
  background:var(--line);border:1px solid var(--line);border-radius:var(--r-xl);overflow:hidden}
@media (max-width:1000px){.rules{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){.rules{grid-template-columns:1fr}}
.rules div{background:var(--surface);padding:30px}
.rules h4{font-family:var(--serif);font-size:19px;margin-bottom:10px}
.rules p{font-size:14px;line-height:1.7;color:var(--text-2)}
.story{display:grid;grid-template-columns:170px minmax(0,1fr);gap:26px;padding:24px 0;
  border-top:1px solid var(--line)}
.story:last-child{border-bottom:1px solid var(--line)}
.story .yr{font-family:var(--serif);font-size:20px;font-weight:700;color:var(--text)}
.story h4{font-family:var(--sans);font-size:15.5px;font-weight:700;margin-bottom:8px}
.story p{font-size:14.5px;line-height:1.7;color:var(--text-2)}
@media (max-width:620px){.story{grid-template-columns:1fr;gap:6px}}
.crew .role{font-size:12.5px;letter-spacing:1.4px;text-transform:uppercase;color:var(--muted);
  font-weight:700;margin-bottom:14px}
.crew p{font-size:14.5px;line-height:1.7;color:var(--text-2)}
{% endblock %}

{% block body %}
<section class="about-hero">
  <div class="shell">
    <p class="kicker">About us</p>
    <h1 style="max-width:22ch">A trekking operator run out of Bengaluru</h1>
    <p class="lede" style="margin-top:16px">
      PEAK runs permitted, guided weekend departures on {{ trek_count }} Karnataka trails across the
      Western Ghats and the Deccan plateau. Batches are capped at fifteen, every departure goes out
      with two guides, and the difficulty grade on each trek page comes from a walk of that route in
      the current season rather than from a brochure.
    </p>
    <div class="tally">
      <div><b>2021</b><span>Year we started</span></div>
      <div><b>{{ trek_count }}</b><span>Trails we run</span></div>
      <div><b>{{ trekker_count }}+</b><span>Trekkers taken out</span></div>
      <div><b>15</b><span>Maximum group size</span></div>
      <div><b>2</b><span>Guides per departure</span></div>
      <div><b>0</b><span>Trailhead fees to pay</span></div>
    </div>
  </div>
</section>

<section class="section section--tight">
  <div class="shell">
    <div class="pair">
      <div>
        <p class="kicker">What we do</p>
        <h2 style="margin-bottom:18px">Six trails, run properly, instead of sixty on a list</h2>
        <div class="prose">
          <p>
            Every trek on this site is one we operate ourselves. We are not a marketplace reselling
            somebody else's batch, so the guide who meets you at the base is on our team, the permit
            in your name was applied for by us, and the person who answers the phone on trek morning
            can actually tell you where your group is.
          </p>
          <p>
            That is also why the list is short. Each trail gets re-walked at the start of a season and
            the trek page gets rewritten from that walk, which is slow work. Adding a seventh trail
            means doing all of it again properly, so we only add one when we can.
          </p>
          <p>
            We operate out of Indiranagar, Bengaluru, and almost everything we run is a weekend
            departure you can do without taking leave: a Saturday or Sunday start, back in the city
            the same night or by the next morning.
          </p>
        </div>
      </div>
      <div>
      <br>
        <p class="kicker">How we work</p>
        <h2 style="margin-bottom:18px">Things we will not do</h2>
        <ul class="ticklist no">
          <li>Take more than fifteen trekkers in a batch, whatever the demand for a date</li>
          <li>Send a batch out with one guide because the second one called in sick</li>
          <li>Soften a difficulty grade to make a trail sell better</li>
          <li>Collect anything extra at the trailhead or at a forest checkpost</li>
          <li>Run a high trail in peak monsoon because a group has already paid</li>
          <li>Light cooking fires, or carry single-use plastic up any route</li>
        </ul>
      </div>
    </div>
  </div>
</section>

<section class="section section--tight">
  <div class="shell">
    <div class="card" style="padding:clamp(30px,4vw,46px);max-width:74ch">
      <p class="kicker" style="margin-bottom:16px">A note from the founder</p>

      <p style="font-size:17.5px;line-height:1.8;color:var(--text-2)">
        PEAK started the way most good weekend plans do: someone suggested a trek, a few people said yes,
        and suddenly we were figuring out who had a car. I liked the trekking part. I did not particularly
        enjoy keeping track of ten people, three different pickup points and everyone's idea of what
        "early morning" meant.
      </p>

      <p style="font-size:17.5px;line-height:1.8;color:var(--text-2);margin-top:16px">
        Somewhere along the way, those little weekend trips turned into PEAK. The idea is still pretty
        simple — find good trails, put together good groups, and make the whole thing easier for people
        who just want to go trekking without spending their entire week planning it.
      </p>

      <p style="font-size:17.5px;line-height:1.8;color:var(--text-2);margin-top:16px">
        I still go out on the trails whenever I can. Partly because I love it, and partly because you learn
        things on a trail that you won't find on a map. A route can look easy on paper and have one
        ridiculous climb halfway through. A "small" stream can become very much not small after rain.
        And sometimes the best part of a trek is the chai you find afterwards.
      </p>

      <p style="font-size:17.5px;line-height:1.8;color:var(--text-2);margin-top:16px">
        We're a small team, and that's intentional. We know the trails, we know the people coming on them,
        and we're around when things don't go exactly according to plan. Which, on a trek, they occasionally
        don't. That's part of the fun too.
      </p>

      <p style="margin-top:24px;font-weight:800;color:var(--text)">
        — Prerana S, Founder
      </p>
    </div>
  </div>
</section>

<section class="section">
  <div class="shell">
    <div class="head">
      <p class="kicker">The crew</p>
      <h2>The people behind the trails</h2>
      <p class="lede" style="margin-top:12px">
        Small team. Too many trekking photos. Very little interest in sitting at a desk all weekend.
      </p>
    </div>

    <div class="crew">

      <div class="who who--lead">
        <span class="avatar">PS</span>
        <div>
          <h3>Prerana S</h3>
          <p class="role">Founder</p>
          <p>
            Started PEAK because organising weekend treks seemed like a better use of time than talking
            about organising weekend treks. Usually the one checking routes, sorting out the details and
            making sure everyone actually knows what they're signing up for. Has a habit of saying
            "it's not that far" immediately before a very long climb.
          </p>
        </div>
      </div>

      <div class="who">
        <span class="avatar">RB</span>
        <h3>Rohit B</h3>
        <p class="role">Lead guide, Western Ghats</p>
        <p>
          Knows the Kudremukh side of the Western Ghats better than most people know their own
          neighbourhood. Fast uphill, annoyingly so, but patient enough to wait for everyone else.
          Has a very practical approach to trekking: check the weather, check the trail, check the group,
          then decide what happens next. Especially good at spotting the "shortcut" that definitely isn't
          a shortcut.
        </p>
      </div>

      <div class="who">
        <span class="avatar">MD</span>
        <h3>Meera D</h3>
        <p class="role">Safety and logistics</p>
        <p>
          The organised one. Knows where the first-aid kit is, when the weather is about to turn and
          exactly how much water people should have brought. Keeps the rest of us from making decisions
          based entirely on optimism. If a trek needs to be changed because of weather, she's usually the
          person who says it first.
        </p>
      </div>

      <div class="who">
        <span class="avatar">AS</span>
        <h3>Arjun S</h3>
        <p class="role">Rock and scramble lead</p>
        <p>
          Give him a rocky trail and he'll probably be happy for the rest of the day. Spends a lot of
          weekends around Savandurga and Ramanagara and has an impressive ability to notice every climb,
          ledge and slightly questionable-looking rock before the rest of us do. Quiet until someone
          asks about climbing. Then you're getting the full explanation.
        </p>
      </div>

      <div class="who">
        <span class="avatar">KN</span>
        <h3>Kavya N</h3>
        <p class="role">Bookings and briefings</p>
        <p>
          The person who makes sure the rest of us know who's coming, where they're coming from and
          whether they've read the trek briefing. If you've messaged PEAK with a question before a trek,
          you've probably spoken to her. Remembers regulars, remembers their favourite trails, and has
          probably answered "what should I wear?" more times than anyone should have to.
        </p>
      </div>

    </div>
  </div>
</section>

<section class="section section--surface">
  <div class="shell">
    <div class="head"><p class="kicker">How we run a departure</p><h2>The same six rules, every trek</h2></div>
    <div class="rules">
      <div><h4>Two guides, always</h4><p>A lead guide at the front and a sweep guide at the back on
        every batch, regardless of size. Both carry a first-aid kit and a whistle, and a route plan is
        left with the office before you set off.</p></div>
      <div><h4>Headcounts at every junction</h4><p>Not only at the start and the finish. On trails with
        side paths that is the difference between noticing someone is missing in two minutes and
        noticing at the summit.</p></div>
      <div><h4>Grades from a real walk</h4><p>Re-walked each season. Savandurga is marked difficult
        because the granite is loose and exposed in three places, and if monsoon damage changes a route
        the grade changes before the next batch, not after.</p></div>
      <div><h4>Permits arranged in advance</h4><p>Kudremukh and Kumara Parvatha sit inside reserve
        forest with a capped daily quota. We apply using the ID details from your booking, and the cost
        is already in the price you saw.</p></div>
      <div><h4>Weather calls the evening before</h4><p>Everyone in the batch is told at the same time.
        A cancelled departure is a full refund or a free date change, your choice. A guide can also stop
        a group mid-trail, and that call is final.</p></div>
      <div><h4>Everything comes back down</h4><p>A waste bag at the base, checked at the end rather
        than just handed out. No cooking fires, no single-use plastic, and rest stops kept away from
        water sources.</p></div>
    </div>
  </div>
</section>

<section class="section">
  <div class="shell">
    <div class="head"><p class="kicker">How we got here</p><h2>Five years, six trails</h2></div>
    <div>
      <div class="story"><div class="yr">2021</div>
        <div><h4>A weekend group becomes a business</h4>
          <p>PEAK registers in Bengaluru and runs its first paid departures on Skandagiri and Nandi
            Hills, with two guides and a borrowed van.</p></div></div>
      <div class="story"><div class="yr">2022</div>
        <div><h4>Into the Western Ghats</h4>
          <p>Kudremukh and Kodachadri are added after a full season of route walks, along with the first
            forest department permit arrangements for reserve-forest trails.</p></div></div>
      <div class="story"><div class="yr">2023</div>
        <div><h4>Granite and the hard grades</h4>
          <p>Savandurga and Kumara Parvatha go on the calendar, and the difficulty grading is rewritten
            so that exposure counts as much as distance.</p></div></div>
      <div class="story"><div class="yr">2024</div>
        <div><h4>Batches capped for good</h4>
          <p>Group size is capped at fifteen across every trail and the two-guide rule becomes absolute,
            even when it means turning down bookings on a popular weekend.</p></div></div>
      <div class="story"><div class="yr">2025</div>
        <div><h4>Booking moves onto this site</h4>
          <p>Dates, quotas, payment and receipts all move online, so a booking is confirmed against a
            real permit quota rather than a spreadsheet someone updates on Monday.</p></div></div>
    </div>
  </div>
</section>

<section class="section section--tight">
  <div class="shell">
    <div class="card" style="text-align:center">
      <h2 style="margin-bottom:12px">Not sure which trail suits you?</h2>
      <p class="lede" style="margin:0 auto 26px">
        Tell us your fitness, your experience and the weekend you have free, and we will say plainly
        which of the {{ trek_count }} trails fits and which one does not.
      </p>
      <div class="row" style="justify-content:center">
        <a href="/contact" class="btn btn--primary">Ask us</a>
        <a href="/treks" class="btn btn--ghost">Browse all treks</a>
      </div>
    </div>
  </div>
</section>
{% endblock %}
"""


TEMPLATES["contact.html"] = """
{% extends "base.html" %}
{% block title %}Contact PEAK{% endblock %}

{% block extra_css %}
.c-layout{display:grid;grid-template-columns:1.25fr 1fr;gap:clamp(36px,4.5vw,66px);align-items:start}
@media (max-width:880px){.c-layout{grid-template-columns:1fr}}
.info div{padding:24px 0;border-bottom:1px solid var(--line)}
.info div:first-child{padding-top:0}
.info h4{font-family:var(--sans);font-size:12px;letter-spacing:1.4px;text-transform:uppercase;
  font-weight:700;color:var(--text);margin-bottom:8px}
.info p{font-size:14.5px;line-height:1.7;color:var(--muted)}
{% endblock %}

{% block body %}
<section class="section section--tight">
  <div class="shell">
    <p class="kicker">Contact</p>
    <h1 style="margin-bottom:12px">Get in touch</h1>
    <p class="lede" style="margin-bottom:38px">
      Questions about fitness, group bookings, or whether a trail is running this weekend.
      Everything sent from this form lands in our inbox and we reply within one working day.
    </p>

    <div class="c-layout">
      <form method="POST" class="card">
        <div class="field-row">
          <div class="field"><label for="name">Your name</label>
            <input id="name" type="text" name="name" value="{{ form.name }}"
                   placeholder="So we know who we are replying to" minlength="2" required></div>
          <div class="field"><label for="email">Email</label>
            <input id="email" type="email" name="email" value="{{ form.email }}"
                   placeholder="you@example.com" required></div>
        </div>
        <div class="field-row">
          <div class="field"><label for="phone">Mobile number</label>
            <input id="phone" type="tel" name="phone" value="{{ form.phone }}"
                   placeholder="Optional, if you would rather we called">
          </div>
          <div class="field"><label for="subject">What is this about</label>
            <select id="subject" name="subject">
              {% for s in subjects %}
                <option value="{{ s }}" {{ 'selected' if form.subject == s }}>{{ s }}</option>
              {% endfor %}
            </select>
          </div>
        </div>
        <div class="field"><label for="message">Your message</label>
          <textarea id="message" name="message" minlength="10"
                    placeholder="Tell us what you need. If it is about a booking you already made, include the reference from your receipt."
                    required>{{ form.message }}</textarea>
          <p class="hint">We reply to the email address above, so do check it is right.</p>
        </div>
        <button class="btn btn--primary" type="submit">Send message</button>
      </form>

      <div class="info">
        <div><h4>Email</h4><p>{{ support_email }}</p><p>Replies within one working day.</p></div>
        <div><h4>Phone</h4><p>{{ support_phone }}, weekdays 10am to 7pm</p></div>
        <div><h4>On trek days</h4><p>Your guide's number goes out with the pre-trek brief, two days before departure.</p></div>
        <div><h4>Office</h4><p>Indiranagar, Bengaluru 560038</p></div>
        <div><h4>Existing bookings</h4><p>Quote the reference printed on your receipt and we can pull the
          booking up straight away. Date changes and cancellations are free up to 72 hours before departure.</p></div>
        <div style="border-bottom:0"><h4>Group bookings</h4><p>Ten or more trekkers, or a private batch on a date of your
          choosing? Mention it in the form and we will quote separately.</p></div>
      </div>
    </div>
  </div>
</section>
{% endblock %}
"""
TEMPLATES["404.html"] = """
{% extends "base.html" %}
{% block title %}404 — Page not found | PEAK{% endblock %}

{% block extra_css %}
.err{max-width:920px;margin:clamp(34px,5vw,70px) auto clamp(60px,7vw,100px);
  border:1px solid var(--line-strong);border-radius:var(--r-2xl);overflow:hidden;
  background:var(--surface);box-shadow:var(--shadow-lg)}
/* 9) the error photo is centred and covers its band */
.err .shot{width:100%;aspect-ratio:16/9;object-fit:cover;object-position:center center;
  border-bottom:1px solid var(--line-strong);background:var(--stone)}
.err .say{padding:clamp(30px,4vw,52px);text-align:center}
.err .say .code{font-size:12px;font-weight:700;letter-spacing:2.4px;text-transform:uppercase;
  color:var(--muted);margin-bottom:14px}
.err .say h1{font-size:clamp(28px,3.4vw,42px);margin-bottom:12px}
.err .say p{color:var(--text-2);max-width:52ch;margin:0 auto 28px}
.err .row{justify-content:center}
{% endblock %}

{% block body %}
<div class="shell">
  <div class="err">
    <img class="shot" src="/error.jpg" alt="Off the trail"
         onerror="this.onerror=null;this.style.display='none'">
    <div class="say">
      <p class="code">Error 404</p>
      <h1>This trail does not exist</h1>
      <p>
        The page or trek you asked for is not here. It may have been moved, or the address
        may have a typo in it.
      </p>
      <div class="row">
        <a href="/" class="btn btn--primary">Back to PEAK</a>
        <a href="/treks" class="btn btn--ghost">See all treks</a>
      </div>
    </div>
  </div>
</div>
{% endblock %}
"""

app.jinja_loader = DictLoader(TEMPLATES)


# ================================================================
# ROUTES
# ================================================================
@app.route("/")
def index():
    featured = (Trek.query.order_by(Trek.featured.desc(), Trek.sort_order.asc())
                .limit(3).all())
    return render_template("home.html", nav="home", featured=featured,
                           hero_photo=HERO_PHOTO,
                           cta_photo=CTA_PHOTO,
                           cta_photo_fallback=PHOTOS["savandurga"]["remote"],
                           trek_count=Trek.query.count(),
                           trekker_count=900 + 7 * Order.query.filter_by(status="paid").count())


@app.route("/treks")
def trek_list():
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "").strip()

    query = Trek.query

    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Trek.name.ilike(like),
                                    Trek.location.ilike(like),
                                    Trek.district.ilike(like),
                                    Trek.state.ilike(like),
                                    Trek.region.ilike(like),
                                    Trek.tagline.ilike(like),
                                    Trek.description.ilike(like)))

    if sort == "price":
        query = query.order_by(Trek.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Trek.price.desc())
    elif sort == "rating":
        query = query.order_by(Trek.rating.desc())
    else:
        query = query.order_by(Trek.featured.desc(), Trek.sort_order.asc())

    return render_template("treks.html", nav="treks", treks=query.all(),
                           total=Trek.query.count(), q=q, sort=sort)


HERO_FOCUS = {}


@app.route("/trek/<slug>")
def trek_detail(slug):
    trek = Trek.query.filter_by(slug=slug).first()
    if not trek:
        return render_template("404.html"), 404

    related = (Trek.query.filter(Trek.id != trek.id)
               .order_by(Trek.featured.desc(), Trek.sort_order.asc()).limit(3).all())

    return render_template("trek.html", nav="treks", trek=trek, related=related,
                           available_dates=get_available_dates(),
                           hero_focus=HERO_FOCUS.get(slug, "center center"))


# ---------------- cart ----------------
@app.route("/cart/add", methods=["POST"])
def cart_add():
    trek = db.session.get(Trek, request.form.get("trek_id", type=int))
    trek_date = request.form.get("trek_date", "").strip()
    people = request.form.get("people", type=int) or 1
    people = max(MIN_PEOPLE, min(people, MAX_PEOPLE))

    if not trek:
        flash("That trek is no longer listed.", "error")
        return redirect("/treks")

    if not valid_trek_date(trek_date):
        flash("Choose one of the listed trek dates before adding it to your cart.", "error")
        return redirect(f"/trek/{trek.slug}")

    existing = CartItem.query.filter_by(cart_key=get_cart_key(), trek_id=trek.id,
                                        trek_date=trek_date).first()
    if existing:
        existing.people = min(existing.people + people, MAX_PEOPLE)
        db.session.commit()
        flash(f"Updated {trek.name} to {existing.people} trekkers.", "success")
    else:
        db.session.add(CartItem(
            cart_key=get_cart_key(), user_id=session.get("user_id"),
            trek_id=trek.id, trek_slug=trek.slug, trek_name=trek.name,
            location=trek.location, image_url=trek.image_url,
            trek_date=trek_date, people=people, price=trek.price))
        db.session.commit()
        flash(f"{trek.name} added to your cart.", "success")
        notify(session.get("user_id"), "Added to cart",
               f"{trek.name} on {pretty_date(trek_date)}.", "info", link="/cart")

    return redirect("/cart")


@app.route("/cart")
def cart_view():
    cart = get_cart()
    subtotal, gst, booking_fee, total = calculate_bill(get_cart_total())

    recent_orders = []
    if session.get("user_id"):
        recent_orders = (Order.query.filter_by(user_id=session["user_id"], status="paid")
                         .order_by(Order.created_at.desc()).limit(3).all())

    return render_template("cart.html", nav="cart", cart=cart, subtotal=subtotal,
                           gst=gst, booking_fee=booking_fee, total=total,
                           recent_orders=recent_orders)


@app.route("/cart/update/<int:item_id>", methods=["POST"])
def cart_update(item_id):
    item = CartItem.query.filter_by(id=item_id, cart_key=get_cart_key()).first()
    if item:
        people = request.form.get("people", type=int) or 1
        item.people = max(MIN_PEOPLE, min(people, MAX_PEOPLE))
        db.session.commit()
        flash(f"{item.trek_name} updated to {item.people} trekkers.", "success")
    return redirect("/cart")


@app.route("/cart/remove/<int:item_id>", methods=["POST"])
def cart_remove(item_id):
    item = CartItem.query.filter_by(id=item_id, cart_key=get_cart_key()).first()
    if item:
        name = item.trek_name
        db.session.delete(item)
        db.session.commit()
        flash(f"{name} removed from your cart.", "info")
    return redirect("/cart")


# ---------------- checkout ----------------
@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    cart = get_cart()
    if not cart:
        session.pop("pending_order_id", None)
        flash("Your cart is empty. Add a trek and a date, then come back to checkout.", "info")
        return redirect("/treks")

    user = g.user  
    subtotal, gst, booking_fee, total = calculate_bill(get_cart_total())

    form = {"name": user.name, "email": user.email, "phone": user.phone or ""}
    selected_method = "card"

    if request.method == "POST":
        form = {
            "name": request.form.get("name", "").strip() or user.name,
            "email": request.form.get("email", "").strip() or user.email,
            "phone": request.form.get("phone", "").strip(),
        }
        selected_method = request.form.get("payment_method", "card")

        if not form["name"] or not form["email"]:
            flash("Enter the name and email the booking should be made under.", "error")
            return redirect("/checkout")

        if not any(ch.isdigit() for ch in form["phone"]):
            flash("Enter a contact number we can reach you on for trek day.", "error")
            return redirect("/checkout")

        for c in cart:
            if not db.session.get(Trek, c.trek_id) or not valid_trek_date(c.trek_date):
                db.session.delete(c)
                db.session.commit()
                flash(f"{c.trek_name} on {pretty_date(c.trek_date)} is no longer "
                      f"available and was removed from your cart.", "error")
                return redirect("/cart")

        if not user.phone and form["phone"]:
            user.phone = form["phone"]
            db.session.commit()

        order = None
        pending_id = session.get("pending_order_id")
        if pending_id:
            candidate = db.session.get(Order, pending_id)
            if candidate and candidate.user_id == user.id:
                if candidate.status == "paid":
                    session.pop("pending_order_id", None)
                    flash("That booking is already paid.", "info")
                    return redirect(f"/order/{candidate.id}/confirmation")
                order = candidate

        if order is None:
            order = Order(order_ref=generate_order_ref(cart),
                          user_id=user.id, name=form["name"], email=form["email"],
                          phone=form["phone"], subtotal=subtotal, gst=gst,
                          booking_fee=booking_fee, total=total, status="pending")
            db.session.add(order)
            db.session.commit()
            session["pending_order_id"] = order.id
        else:
            order.name, order.email, order.phone = form["name"], form["email"], form["phone"]
            order.subtotal, order.gst = subtotal, gst
            order.booking_fee, order.total = booking_fee, total
            order.status = "pending"

        OrderItem.query.filter_by(order_id=order.id).delete()
        for c in cart:
            db.session.add(OrderItem(order_id=order.id, trek_id=c.trek_id,
                                     trek_slug=c.trek_slug, trek_name=c.trek_name,
                                     location=c.location, image_url=c.image_url,
                                     trek_date=c.trek_date, people=c.people, price=c.price))
        db.session.commit()

        if selected_method == "upi":
            upi_id = request.form.get("upi_id", "").strip()
            result = process_test_upi_payment(upi_id, total)
            method_label = "UPI"
        else:
            upi_id = None
            result = process_test_card_payment(request.form.get("card_number", ""),
                                               request.form.get("expiry", ""),
                                               request.form.get("cvv", ""), total)
            method_label = "Test card"

        payment = Payment(
            order_id=order.id,
            transaction_id=result.get("transaction_id") or f"FAIL-{uuid.uuid4().hex[:12].upper()}",
            payment_method=selected_method, method=method_label,
            upi_id=upi_id if selected_method == "upi" else None,
            amount=total, status="success" if result["success"] else "failed",
            gateway_message=result["message"])
        db.session.add(payment)

        if result["success"]:
            order.status = "paid"
            db.session.commit()
            session.pop("pending_order_id", None)

            notify(user.id, "Booking confirmed",
                   f"{order.order_ref} is paid. Details are in your email.",
                   "success", link=f"/order/{order.id}/confirmation")

            CartItem.query.filter_by(cart_key=get_cart_key()).delete()
            db.session.commit()

            send_receipt_email(order, payment)
            flash("Payment approved. Your booking is confirmed.", "success")
            return redirect(f"/order/{order.id}/confirmation")

        order.status = "failed"
        db.session.commit()
        notify(user.id, "Payment did not go through",
               f"{order.order_ref}: {result['message']}", "error",
               link=f"/order/{order.id}/confirmation")
        flash(result["message"] + " Your cart is untouched, so you can try again.", "error")

    return render_template("checkout.html", nav="cart", cart=cart, form=form,
                           subtotal=subtotal, gst=gst, booking_fee=booking_fee,
                           total=total, selected_method=selected_method,
                           qr_data_uri=generate_upi_qr_data_uri(total))


@app.route("/order/<int:order_id>/confirmation")
def order_confirmation(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return render_template("404.html"), 404

    if order.user_id and order.user_id != session.get("user_id"):
        flash("Sign in with the account that made this booking to see it.", "info")
        return redirect(url_for("signin", next=request.path))

    payment = order.latest_payment()
    if not payment:
        return render_template("404.html"), 404

    return render_template("confirmation.html", nav="cart", order=order,
                           payment=payment, paid=(order.status == "paid"))


@app.route("/bookings")
@login_required
def bookings():
    orders = (Order.query.filter_by(user_id=session["user_id"])
              .order_by(Order.created_at.desc()).all())

    paid = [o for o in orders if o.status == "paid"]
    stats = {
        "paid": len(paid),
        "people": sum(o.headcount() for o in paid),
        "spent": sum(o.total for o in paid),
        "failed": len([o for o in orders if o.status != "paid"]),
    }
    return render_template("bookings.html", nav="bookings", orders=orders, stats=stats)


# ---------------- auth ----------------
def safe_next(raw):
    """Only allow same-site redirects."""
    if raw and raw.startswith("/") and not raw.startswith("//"):
        return raw.rstrip("?")
    return "/"


@app.route("/signup", methods=["GET", "POST"])
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
            return redirect(url_for("signin", next=next_url))
        else:
            user = User(name=form["name"], email=form["email"], phone=form["phone"],
                        password=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()

            session["user_id"] = user.id
            merge_cart_into_account(user)
            notify(user.id, "Welcome to PEAK",
                   "Your account is ready. Pick a trail and a weekend.", "success", link="/treks")
            flash(f"Account created. Welcome aboard, {user.name.split()[0]}.", "success")
            return redirect(next_url if next_url != "/" else "/treks")

    return render_template("auth.html", nav="auth", mode="signup", form=form,
                           next_url=next_url,
                           art=AUTH_PHOTO_SIGNUP,
                           art_fallback=PHOTOS["kodachadri"]["remote"])


@app.route("/signin", methods=["GET", "POST"])
def signin():
    form = {"name": "", "email": "", "phone": ""}
    next_url = safe_next(request.values.get("next"))

    if request.method == "POST":
        form["email"] = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=form["email"]).first()

        if not user or not check_password_hash(user.password, password):
            flash("That email and password combination did not match an account.", "error")
        else:
            session["user_id"] = user.id
            merge_cart_into_account(user)
            flash(f"Signed in. Good to see you, {user.name.split()[0]}.", "success")
            return redirect(next_url)

    return render_template("auth.html", nav="auth", mode="signin", form=form,
                           next_url=next_url,
                           art=AUTH_PHOTO_SIGNIN,
                           art_fallback=PHOTOS["skandagiri"]["remote"])


@app.route("/logout")
def logout():

    session.pop("user_id", None)
    session.pop("cart_key", None)
    session.pop("pending_order_id", None)
    flash("Signed out. Your cart is saved to your account.", "info")
    return redirect("/")


# ---------------- notifications ----------------
@app.route("/notifications/open/<int:notif_id>")
def open_notification(notif_id):
    n = Notification.query.filter_by(id=notif_id, user_id=session.get("user_id")).first()
    if not n:
        return redirect("/")
    n.is_read = True
    db.session.commit()
    return redirect(n.link or request.referrer or "/")


# ---------------- static pages ----------------
@app.route("/about")
def about():
    return render_template("about.html", nav="about", trek_count=Trek.query.count(),
                           trekker_count=900 + 7 * Order.query.filter_by(status="paid").count())


SUBJECT_OPTIONS = [
    "A booking I already made",
    "Choosing the right trek",
    "Group or corporate booking",
    "Refund or date change",
    "Fitness or difficulty question",
    "Something else",
]


@app.route("/contact", methods=["GET", "POST"])
def contact():
    user = current_user()
    form = {
        "name": user.name if user else "",
        "email": user.email if user else "",
        "phone": user.phone if user else "",
        "subject": SUBJECT_OPTIONS[0],
        "message": "",
    }

    if request.method == "POST":
        form = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "subject": request.form.get("subject", "").strip() or SUBJECT_OPTIONS[0],
            "message": request.form.get("message", "").strip(),
        }

        errors = []
        if len(form["name"]) < 2:
            errors.append("Please give a name we can use in the reply.")
        email = form["email"]
        if "@" not in email or "." not in email.split("@")[-1] or len(email) < 6:
            errors.append("That email address does not look right, so we would not be able to reply.")
        if len(form["message"]) < 10:
            errors.append("Tell us a little more in the message so we can actually answer it.")
        if form["subject"] not in SUBJECT_OPTIONS:
            form["subject"] = SUBJECT_OPTIONS[-1]

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("contact.html", nav="contact", form=form,
                                   subjects=SUBJECT_OPTIONS, support_email=ENQUIRY_INBOX,
                                   support_phone=SUPPORT_PHONE)

        enquiry = Enquiry(name=form["name"], email=form["email"], phone=form["phone"],
                          subject=form["subject"], message=form["message"])
        db.session.add(enquiry)
        db.session.commit()

        sent = send_enquiry_email(enquiry)
        if sent:
            enquiry.emailed = True
            db.session.commit()
            send_enquiry_ack(enquiry)

        if user:
            notify(user.id, "Message sent",
                   f"We have your message about {enquiry.subject.lower()}. Reference ENQ-{enquiry.id}.",
                   "success", link="/contact")

        if sent:
            flash(f"Message sent. Your reference is ENQ-{enquiry.id} and we reply "
                  f"within one working day.", "success")
        else:
            flash(f"Your message is saved with reference ENQ-{enquiry.id}, but our mail "
                  f"server did not accept it just now. If it is urgent, call "
                  f"{SUPPORT_PHONE}.", "error")
        return redirect("/contact")

    return render_template("contact.html", nav="contact", form=form,
                           subjects=SUBJECT_OPTIONS, support_email=ENQUIRY_INBOX,
                           support_phone=SUPPORT_PHONE)


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


# ================================================================
# SEED DATA
# ================================================================
def wiki_photo(filename, width=1400):
    """Wikimedia Commons image of a specific place, served at a sane width.
    Special:FilePath redirects to the current file, so these do not rot when a
    file is re-uploaded."""
    return (f"https://commons.wikimedia.org/wiki/Special:FilePath/"
            f"{quote(filename)}?width={width}")

PHOTOS = {
    "kudremukh": {
        "local": "/kudremukh.jpg",
        "remote": wiki_photo("Kudremukh National Park.jpg"),
        "gallery": [
            wiki_photo("Beautiful Kudremukha trek Buddha rock.jpg", 1000),
            wiki_photo("Shola Grasslands and forests in the Kudremukh National Park, Western Ghats, Karnataka.jpg", 1000),
            wiki_photo("Mountains of Kudremukh.jpg", 1000),
            wiki_photo("A view from South Kanara border in the Kudremukh National Park.jpg", 800),
            wiki_photo("Blue skies and green hills (23317241020).jpg", 800),
            wiki_photo("Leaving the peak behind. (22986181353).jpg", 800),
        ],
    },
    "kumara-parvatha": {
        "local": "/kumara%20parvatha.jpg",
        "remote": wiki_photo("Kumara parvatha.jpg"),
        "gallery": [
            wiki_photo("Kumara Parvatha cliff.JPG", 1000),
            wiki_photo("This is the beautiful view of Kumara parvatha.jpg", 1000),
            wiki_photo("Kumara parvatha.jpg", 1000),
            wiki_photo("Trekking5.jpg", 800),
            wiki_photo("Trekking7.jpg", 800),
        ],
    },
    "savandurga": {
        "local": "/savandurga.png",
        "remote": wiki_photo("Savandurga Hill 01.jpg"),
        "gallery": [
            wiki_photo("On the way to Savandurga (3692301065).jpg", 1000),
            wiki_photo("Panhole Savandurga1.jpg", 1000),
            wiki_photo("Savandurga Hill 01.jpg", 1000),
            wiki_photo("Savandurga forest.jpg", 800),
            wiki_photo("Savandurga temple.jpg", 800),
            wiki_photo("Savandurga waterfall.jpg", 800),
        ],
    },
    "skandagiri": {
        "local": wiki_photo("Cloud over Skandagiri hills.jpg"),
        "remote": wiki_photo("Skandagiri Hills.jpg"),
        "gallery": [
            wiki_photo("Skandagiri hills top in Chikkaballapur district -1.jpg", 1000),
            wiki_photo("Skandagiri hills top in Chikkaballapur district -2.jpg", 1000),
            wiki_photo("Cloud over Skandagiri hills.jpg", 1000),
            wiki_photo("Skandagiri Trek Forest Reception Counter 3.jpg", 800),
            wiki_photo("Skandagiri Hills.jpg", 800),
        ],
    },
    "kodachadri": {
        "local": wiki_photo("Kodachadri hills.jpg"),
        "remote": wiki_photo("Kodachadri, Shivamogga, Karnataka, India 7366 (14186531550).jpg"),
        "gallery": [
            wiki_photo("Kodachadri, Shivamogga, Karnataka, India 7366 (14186531550).jpg", 1000),
            wiki_photo("Kodachadri hills.jpg", 1000),
            wiki_photo("Kodachadri.JPG", 1000),
            wiki_photo("Beautiful sights (49005366603).jpg", 800),
        ],
    },
    "nandi-hills-sunrise": {
        "local": wiki_photo("Nandi hills top view.jpg"),
        "remote": wiki_photo("Nandhi Hills.jpg"),
        "gallery": [
            wiki_photo("Nandi hills top view.jpg", 1000),
            wiki_photo("Nandhi Hills.jpg", 1000),
            wiki_photo("Nandi at Nandi Hills-1.jpg", 1000),
            wiki_photo("Enjoying the Beauty of Nandi hills in Wet Monsoon.jpg", 800),
            wiki_photo("Nehru Nilaya @ Nandi Hills.jpg", 800),
            wiki_photo("Ancient writings on the walls of a cave, Nandi Hills, Chikkaballapur, Karnataka (2014).jpg", 800),
        ],
    },
}

HERO_PHOTO = PHOTOS["kudremukh"]["remote"]


def seed_treks():
    treks = [
        Trek(
            slug="kudremukh", district="Chikkamagaluru", state="Karnataka", sort_order=1, featured=True,
            name="Kudremukh", location="Chikkamagaluru, Karnataka", region="Western Ghats",
            tagline="Twenty kilometres of rolling grassland and shola forest, ending on the horse-faced ridge.",
            description="Kudremukh is the classic Western Ghats grassland trek: a long, undulating walk through "
                        "shola pockets, three stream crossings and open ridge after open ridge, finishing on a "
                        "summit named for the horse-face profile it shows from the west.",
            long_description=(
                "The trail starts behind Mullodi village and climbs gently for the first hour through coffee and "
                "cardamom, before the canopy opens and the grassland takes over. From there it is exposed the whole "
                "way, which is exactly why the October to February window matters so much."
                "|| Distance is the real difficulty here rather than gradient. Twenty kilometres round trip on soft, "
                "tussocky ground works your ankles harder than a shorter, steeper climb would. Most groups take five "
                "to six hours up and four down."
                "|| The forest department caps daily entries and requires you to be off the trail well before dark, "
                "so we start at first light. That also buys you the best chance of a clear summit before the cloud "
                "builds up through the afternoon."),
            price=2449, difficulty="Moderate, long day on foot", difficulty_band="Moderate",
            duration="1 day", distance="20 km round trip", altitude="1,892 m",
            group_size="8 - 15 trekkers",
            starting_point="Mullodi village", ending_point="Kudremukh peak",
            best_season="October to February",
            how_to_reach="Mullodi is reached via Kalasa, roughly 330 km from Bengaluru and 130 km from Mangaluru. "
                         "Overnight buses run to Kalasa; from there it is a 12 km jeep ride on a rough track to the "
                         "homestay at Mullodi, which we arrange as part of the booking.",
            highlights="The horse-face profile from the final ridge; three stream crossings; shola forest pockets; "
                       "grassland that runs to the horizon; Lakya dam views on a clear day; sunrise from the second ridge",
            things_to_carry="Trekking shoes with deep tread; 3 litres of water; packed lunch and energy snacks; "
                            "rain shell even outside monsoon; sunscreen and a cap; personal medication; a walking stick if your knees prefer one",
            inclusions="Forest department entry and trekking permit; lead guide and sweep guide; homestay breakfast at Mullodi; "
                       "jeep transfer from Kalasa to Mullodi and back; first-aid support; waste bags for the group",
            exclusions="Travel from your city to Kalasa; lunch on the trail; personal gear and rain wear; "
                       "anything you buy in the village; travel insurance",
            safety_info="The grassland is fully exposed with no shade and no water source after the second stream, so "
                        "ration your water. After rain the black-soil sections turn greasy and the descent is where "
                        "most slips happen. Turnaround time is 1pm regardless of how close the summit looks.",
            permit_info="Trekking inside Kudremukh National Park needs a forest department permit, and daily entries "
                        "are capped. Carry a government photo ID; the name must match the booking. Camping is not "
                        "permitted anywhere inside the park.",
            itinerary=json.dumps([
                {"when": "Previous night", "title": "Reach Kalasa", "text": "Overnight bus from Bengaluru. We meet you at Kalasa and jeep across to the Mullodi homestay."},
                {"when": "6:00 am", "title": "Briefing and breakfast", "text": "Route brief, water check and a hot breakfast. Packed lunch goes into your bag here."},
                {"when": "6:45 am", "title": "Start the climb", "text": "Gentle plantation trail for the first hour, then out into the open grassland."},
                {"when": "9:30 am", "title": "Stream crossings", "text": "Three crossings in quick succession. Last reliable water point, so fill up here."},
                {"when": "12:00 pm", "title": "Summit", "text": "The final ridge walk and the horse-face view. Lunch at the top if the wind allows."},
                {"when": "1:00 pm", "title": "Turn around", "text": "Hard turnaround time. The descent is long and we want everyone down in daylight."},
                {"when": "5:00 pm", "title": "Back at Mullodi", "text": "Tea, a wash, and the jeep back to Kalasa for your onward bus."},
            ]),
            faqs=json.dumps([
                {"q": "Is this a good first trek?", "a": "Only if you already walk 8 to 10 km comfortably. The gradient is kind but the distance is not, and there is no short version once you are on the ridge."},
                {"q": "Are leeches a problem?", "a": "Between June and September, badly. In the October to February window you will rarely see one. Salt or Dettol on your socks handles the stragglers."},
                {"q": "Can I camp at the summit?", "a": "No. Camping is banned inside the national park and the forest department checks. We stay at the Mullodi homestay instead."},
                {"q": "What if the weather turns?", "a": "We call it 24 hours ahead. If the trail is unsafe you get a free date change or a full refund, your choice."},
            ]),
            gallery=json.dumps(PHOTOS["kudremukh"]["gallery"]),
            image_url=PHOTOS["kudremukh"]["local"], fallback_image=PHOTOS["kudremukh"]["remote"],
            rating=4.9, reviews_count=214,
        ),
        Trek(
            slug="kumara-parvatha", district="Dakshina Kannada", state="Karnataka", sort_order=2, featured=True,
            name="Kumara Parvatha", location="Kukke Subramanya, Karnataka", region="Western Ghats",
            tagline="Karnataka's hardest weekend climb: two days, three false summits and a night at Bhattara Mane.",
            description="A two-day climb from Kukke Subramanya through dense forest, a brutal open stretch known as "
                        "the Kallu Mantapa section, and a final push over Shesha Parvatha to the Kumara Parvatha summit.",
            long_description=(
                "There is a reason this one has a reputation. The first half is forest, steep and humid but shaded. "
                "Past Bhattara Mane the trees stop and the trail becomes a series of rock steps and grass slopes with "
                "the sun full on you, and the summit keeps hiding behind one more rise."
                "|| We break the climb with a night at Bhattara Mane, the forest house partway up where the family has "
                "been feeding trekkers for decades. Simple food, a floor to sleep on, and an early start the next day."
                "|| Come with some training behind you. If you can do a stair-climbing session and a 10 km walk in the "
                "same week without much complaint, you will enjoy this. If not, take Skandagiri first and come back."),
            price=2749, difficulty="Difficult, steep and sustained", difficulty_band="Difficult",
            duration="2 days", distance="28 km round trip", altitude="1,712 m",
            group_size="6 - 12 trekkers",
            starting_point="Kukke Subramanya", ending_point="Kumara Parvatha summit",
            best_season="October to February",
            how_to_reach="Kukke Subramanya is about 280 km from Bengaluru and 105 km from Mangaluru, with overnight "
                         "KSRTC buses running directly to the temple town. The trail head is a ten minute walk from "
                         "the bus stand.",
            highlights="Bhattara Mane, the forest house that feeds every trekker on the hill; Girigadde viewpoint; "
                       "the Shesha Parvatha false summit; sunrise above the cloud line; the Pushpagiri sanctuary forest; "
                       "views into Kodagu on a clear morning",
            things_to_carry="Broken-in trekking shoes, not new ones; 4 litres of water capacity; headlamp with spare "
                            "batteries; warm layer for the night; toilet paper and a trowel; electrolyte sachets; "
                            "a change of clothes for the second day",
            inclusions="Forest department permit and entry; lead guide and sweep guide; overnight stay and meals at "
                       "Bhattara Mane; dinner, breakfast and next-day packed lunch; first-aid support; waste bags",
            exclusions="Travel to and from Kukke Subramanya; lunch on day one; sleeping bag hire; personal gear; "
                       "temple darshan and any local expenses",
            safety_info="This is a physically demanding climb with a long committing section above the tree line. "
                        "Heat exhaustion is the most common problem we see, not falls. Drink before you are thirsty, "
                        "and tell the sweep guide early if you are struggling rather than at the top.",
            permit_info="Forest department permission is required and is arranged with your booking. Carry photo ID. "
                        "Camping on the summit is prohibited; the only permitted overnight stop is Bhattara Mane. "
                        "Plastic is checked at the forest gate.",
            itinerary=json.dumps([
                {"when": "Day 1, 7:00 am", "title": "Meet at Kukke", "text": "Breakfast in town, gear check and the forest gate formalities."},
                {"when": "Day 1, 8:30 am", "title": "Into the forest", "text": "Steep, shaded and humid. Slow and steady pace to Bhattara Mane."},
                {"when": "Day 1, 1:00 pm", "title": "Bhattara Mane", "text": "Lunch, rest, and an easy afternoon. Optional walk up to Girigadde for the evening view."},
                {"when": "Day 1, 8:00 pm", "title": "Dinner and lights out", "text": "Home-cooked meal and an early night on the floor. Bring your own bedding roll."},
                {"when": "Day 2, 4:30 am", "title": "Summit push", "text": "Headlamps on. Kallu Mantapa, then Shesha Parvatha, then the real summit."},
                {"when": "Day 2, 7:30 am", "title": "Sunrise at the top", "text": "Above the cloud line on a good morning, with Kodagu spread out to the north."},
                {"when": "Day 2, 3:00 pm", "title": "Back in Kukke", "text": "Long descent, a wash, and buses back to the city."},
            ]),
            faqs=json.dumps([
                {"q": "How fit do I need to be?", "a": "Fitter than for anything else on this site. Six to eight hours of climbing on day one and an early summit push on day two, both with a pack."},
                {"q": "What are the toilets like?", "a": "Basic at Bhattara Mane and nothing at all above it. Carry toilet paper and a trowel, and bury everything well off the trail."},
                {"q": "Can I do it in one day?", "a": "Experienced trekkers do, but we do not run it that way. The two-day version is safer and you actually get to enjoy the top."},
                {"q": "Is there mobile signal?", "a": "Patchy at Bhattara Mane, nothing on the climb. Tell someone at home your schedule before you start."},
            ]),
            gallery=json.dumps(PHOTOS["kumara-parvatha"]["gallery"]),
            image_url=PHOTOS["kumara-parvatha"]["local"], fallback_image=PHOTOS["kumara-parvatha"]["remote"],
            rating=4.8, reviews_count=176,
        ),
        Trek(
            slug="savandurga", district="Ramanagara", state="Karnataka", sort_order=3, featured=True,
            name="Savandurga", location="Magadi, Ramanagara", region="Deccan plateau",
            tagline="One of Asia's largest monoliths, climbed straight up bare rock in under three hours.",
            description="A short, steep scramble up an enormous granite dome an hour from Bengaluru, past the ruins "
                        "of a Kempegowda-era fort to a summit with the entire Ramanagara countryside laid out below.",
            long_description=(
                "Savandurga is deceptive. Four and a half kilometres sounds like nothing, and then you are on open "
                "rock at a gradient that has you using your hands, with white paint marks as the only trail."
                "|| The grip of your shoes matters more here than on any other trail we run. The granite is excellent "
                "when dry and genuinely dangerous when wet, which is why we do not run this one in the monsoon at all."
                "|| Because it is close to the city we start very early, summit by sunrise and are back down before "
                "the rock heats up. In summer the surface temperature at 10am is high enough to be unpleasant through "
                "thin soles."),
            price=849, difficulty="Difficult, steep exposed rock", difficulty_band="Difficult",
            duration="3 hours up and down", distance="4.5 km round trip", altitude="1,226 m",
            group_size="8 - 15 trekkers",
            starting_point="Bettada Dari trail head", ending_point="Kempegowda fort summit",
            best_season="October to February",
            how_to_reach="Savandurga is 55 km from Bengaluru via Magadi Road, about 90 minutes by car. Buses run to "
                         "Magadi, with autos covering the last 12 km. Most groups leave the city at 4am to be on the "
                         "rock before sunrise.",
            highlights="Sunrise from the summit with Manchanabele reservoir below; Kempegowda fort ruins; the Nandi "
                       "shrine near the top; vulture nesting cliffs on the far face; a genuine rock scramble within "
                       "an hour of the city",
            things_to_carry="Shoes with soft, grippy soles, not hiking boots with hard treads; 2 litres of water; "
                            "a light breakfast to eat at the top; cap and sunscreen; a small daypack that does not swing",
            inclusions="Eco-tourism entry fee; lead guide and sweep guide; pre-climb briefing on the rock section; "
                       "first-aid support; waste bags for the group",
            exclusions="Transport from Bengaluru; food and water; personal gear; anything at the base village",
            safety_info="The exposed rock section is the crux and it is unforgiving in the wet, so we cancel rather "
                        "than run it after rain. Keep three points of contact on the steep slabs, descend facing the "
                        "rock where the angle is high, and do not wander towards the edges for photographs.",
            permit_info="Savandurga has an official Karnataka eco-tourism trail with a gate fee and fixed opening "
                        "hours. Entry closes in the early afternoon and the trail must be cleared by evening.",
            itinerary=json.dumps([
                {"when": "4:00 am", "title": "Leave Bengaluru", "text": "Pickup from a central point. Coffee stop on Magadi Road."},
                {"when": "5:30 am", "title": "Base and briefing", "text": "Gate formalities, shoe check and a short talk about the rock section."},
                {"when": "5:45 am", "title": "Start climbing", "text": "Scrub and boulders at first, then straight onto open granite following the white marks."},
                {"when": "7:00 am", "title": "Summit and sunrise", "text": "Fort ruins, the Nandi shrine and breakfast with the reservoir below."},
                {"when": "8:15 am", "title": "Descend", "text": "Slower than the climb. We take the steep slabs one at a time as a group."},
                {"when": "10:00 am", "title": "Back in the city", "text": "Down before the rock gets hot, home before lunch."},
            ]),
            faqs=json.dumps([
                {"q": "Why is a 4.5 km trek graded difficult?", "a": "Because of the angle and the exposure, not the distance. Long stretches are bare rock steep enough to need your hands."},
                {"q": "Can beginners do it?", "a": "Fit beginners with no fear of heights, yes. If exposure bothers you, Skandagiri or Nandi Hills is the better call."},
                {"q": "What shoes should I wear?", "a": "Running shoes with soft rubber grip better on granite than stiff hiking boots. Worn-smooth soles are the single biggest risk."},
                {"q": "Do you run it in the monsoon?", "a": "No. Wet granite here is genuinely dangerous and we do not take the chance."},
            ]),
            gallery=json.dumps(PHOTOS["savandurga"]["gallery"]),
            image_url=PHOTOS["savandurga"]["local"], fallback_image=PHOTOS["savandurga"]["remote"],
            rating=4.7, reviews_count=308,
        ),
        Trek(
            slug="skandagiri", district="Chikkaballapur", state="Karnataka", sort_order=4,
            name="Skandagiri", location="Chikkaballapur, Karnataka", region="Deccan plateau",
            tagline="A night climb to a ruined fort, timed so you reach the top as the cloud sea lights up.",
            description="Also called Kalavara Durga, Skandagiri is the classic Bengaluru night trek: a moderate "
                        "torch-lit climb through scrub and boulders to a Tipu-era fort, arriving in time for sunrise "
                        "over a valley that fills with cloud in winter.",
            long_description=(
                "The appeal is the timing. You start around 2am, climb by headlamp with the lights of Chikkaballapur "
                "behind you, and reach the fort walls while it is still dark. Then the valley below turns white and "
                "the sun comes up through it."
                "|| The trail itself is straightforward: a defined path, some loose rock, a few short scrambles near "
                "the top. What catches people out is doing it on no sleep, in the dark, in the cold."
                "|| Winter is when the cloud inversion actually happens. Outside December to February you still get a "
                "fine sunrise, just without the sea of cloud that Skandagiri is known for."),
            price=1049, difficulty="Moderate, night climb", difficulty_band="Moderate",
            duration="5 hours, overnight start", distance="8 km round trip", altitude="1,450 m",
            group_size="8 - 15 trekkers",
            starting_point="Papagni Mutt, Chikkaballapur", ending_point="Skandagiri fort ruins",
            best_season="December to February",
            how_to_reach="Chikkaballapur is 60 km north of Bengaluru on NH44, about 75 minutes by road. The trail "
                         "head at Papagni Mutt is a further 15 minutes from town on a narrow village road.",
            highlights="The winter cloud inversion at sunrise; Tipu-era fort walls and cisterns; climbing entirely by "
                       "headlamp; Nandi Hills visible across the valley; a small temple at the summit",
            things_to_carry="Headlamp, not a phone torch; warm layer and a windproof top; 2 litres of water; snacks "
                            "for the summit wait; shoes with grip for loose gravel; a light blanket if you feel the cold",
            inclusions="Forest department night entry permit; lead guide and sweep guide; hot tea at the summit; "
                       "first-aid support; waste bags for the group",
            exclusions="Transport from Bengaluru; breakfast; headlamp hire; personal warm layers",
            safety_info="Night climbing means the main risks are a twisted ankle on loose rock and getting separated "
                        "from the group. Stay between the two guides, keep your light on the ground rather than in "
                        "people's eyes, and it gets cold and windy at the top while you wait for sunrise.",
            permit_info="Night trekking here requires forest department permission and is only allowed with a "
                        "registered operator. Entry is checked at the base and headcounts are taken both ways.",
            itinerary=json.dumps([
                {"when": "11:30 pm", "title": "Leave Bengaluru", "text": "Pickup from a central point, drive up NH44."},
                {"when": "1:30 am", "title": "Base check", "text": "Permit formalities, headlamp check and a briefing on staying together in the dark."},
                {"when": "2:00 am", "title": "Start climbing", "text": "Scrub and boulder trail by torchlight, with a couple of short scrambles near the fort."},
                {"when": "4:30 am", "title": "Reach the fort", "text": "Find a sheltered spot behind the walls, layer up and wait. Hot tea comes out here."},
                {"when": "6:15 am", "title": "Sunrise", "text": "The valley fills with cloud on a good winter morning and the sun comes up through it."},
                {"when": "9:00 am", "title": "Back at the base", "text": "Descend in daylight, which is a completely different trail to the one you climbed."},
            ]),
            faqs=json.dumps([
                {"q": "Will I definitely see the cloud sea?", "a": "No, and anyone promising it is lying. It needs cold, still, humid winter mornings. December to February gives you the best odds."},
                {"q": "Is a phone torch enough?", "a": "No. You need both hands free on the scramble sections. A proper headlamp is required, not optional."},
                {"q": "How cold does it get?", "a": "Single digits at the summit in December and January, with wind. People underestimate the wait between arriving and sunrise."},
                {"q": "Can I sleep at the top?", "a": "Overnight camping is not permitted. The climb is timed so the wait is about ninety minutes."},
            ]),
            gallery=json.dumps(PHOTOS["skandagiri"]["gallery"]),
            image_url=PHOTOS["skandagiri"]["local"], fallback_image=PHOTOS["skandagiri"]["remote"],
            rating=4.6, reviews_count=241,
        ),
        Trek(
            slug="kodachadri", district="Shivamogga", state="Karnataka", sort_order=5,
            name="Kodachadri", location="Shivamogga, Karnataka", region="Western Ghats",
            tagline="Ghat forest, an old iron pillar on a grassy summit, and the sea visible on a clear evening.",
            description="A shola and grassland climb inside the Mookambika wildlife sanctuary, finishing at the "
                        "Sarvajna Peetha shrine and an iron pillar that has stood on the summit for centuries, with "
                        "the Arabian Sea on the horizon.",
            long_description=(
                "Kodachadri sits right at the western edge of the Ghats, which is why the view is different from "
                "anything else on this list. On a clear evening you can pick out the coastline from the top."
                "|| The trail climbs through thick evergreen forest before opening into grassland for the last stretch. "
                "There is a jeep track that goes most of the way, which we ignore; the walking route through the forest "
                "is the whole point."
                "|| Hidlumane falls sits just off the trail and is worth the short detour outside the driest months. "
                "It is a scramble over wet rock, so it is optional and we go in small groups."),
            price=2349, difficulty="Moderate, steady forest climb", difficulty_band="Moderate",
            duration="1 day", distance="14 km round trip", altitude="1,343 m",
            group_size="8 - 14 trekkers",
            starting_point="Nittur base village", ending_point="Sarvajna Peetha, Kodachadri summit",
            best_season="October to February",
            how_to_reach="Nittur is near Kollur in Shivamogga district, roughly 400 km from Bengaluru. Overnight buses "
                         "run to Kollur, and the base village is 20 km further by local jeep, which we arrange.",
            highlights="Hidlumane falls on the lower trail; the iron pillar at Sarvajna Peetha; the Arabian Sea on the "
                       "horizon at sunset; evergreen shola forest; Mookambika sanctuary birdlife; grassland ridge walking",
            things_to_carry="Trekking shoes that handle wet rock; 3 litres of water; packed lunch; rain shell; "
                            "quick-dry clothes if you plan to do the falls; sunscreen; personal medication",
            inclusions="Sanctuary entry and trekking permit; lead guide and sweep guide; jeep transfer from Kollur to "
                       "Nittur and back; breakfast at the base; first-aid support; waste bags",
            exclusions="Travel to and from Kollur; lunch; accommodation before or after; personal gear",
            safety_info="The Hidlumane falls detour is over slick rock and is the most common place for injuries on "
                        "this trail, so it is optional and guided in small groups. Above the tree line the wind picks "
                        "up sharply in the evening. Leeches are common on the forest section after any rain.",
            permit_info="Kodachadri lies inside the Mookambika wildlife sanctuary and needs a forest department entry "
                        "permit, arranged with your booking. Plastic is checked at the gate and camping inside the "
                        "sanctuary is not allowed.",
            itinerary=json.dumps([
                {"when": "Previous night", "title": "Bus to Kollur", "text": "Overnight from Bengaluru. We meet you at Kollur in the morning."},
                {"when": "7:00 am", "title": "Breakfast at Nittur", "text": "Jeep transfer to the base village, breakfast and the sanctuary gate formalities."},
                {"when": "8:00 am", "title": "Into the forest", "text": "Steady climb through evergreen forest, thick canopy and stream crossings."},
                {"when": "10:00 am", "title": "Hidlumane falls", "text": "Optional detour in small groups. Wet rock scramble, worth it outside the dry months."},
                {"when": "12:30 pm", "title": "Grassland and summit", "text": "Out of the trees and along the ridge to the iron pillar and the shrine."},
                {"when": "2:00 pm", "title": "Start down", "text": "Same route back through the forest, slower on the wet sections."},
                {"when": "5:30 pm", "title": "Back at Nittur", "text": "Tea, jeep to Kollur, and the evening bus home."},
            ]),
            faqs=json.dumps([
                {"q": "Can I just take the jeep up?", "a": "Jeeps run to near the summit, but then it is a drive, not a trek. Our booking is for the walking route."},
                {"q": "Are leeches bad here?", "a": "In and just after the monsoon, yes. Anti-leech socks or salt on your ankles handles it. By December they are mostly gone."},
                {"q": "Can we swim at the falls?", "a": "A dip in the lower pool when the flow is gentle, under guide supervision. Not in high flow, and never alone."},
                {"q": "Will I actually see the sea?", "a": "On a clear, dry-season evening, usually. In haze or cloud, no. It is a bonus rather than the reason to come."},
            ]),
            gallery=json.dumps(PHOTOS["kodachadri"]["gallery"]),
            image_url=PHOTOS["kodachadri"]["local"], fallback_image=PHOTOS["kodachadri"]["remote"],
            rating=4.8, reviews_count=132,
        ),
        Trek(
            slug="nandi-hills-sunrise", district="Chikkaballapur", state="Karnataka", sort_order=6,
            name="Nandi Hills sunrise walk", location="Chikkaballapur, Karnataka", region="Deccan plateau",
            tagline="The gentlest trail we run: 1,200 stone steps, a summer palace at the top, home by breakfast.",
            description="A short stepped climb up the old Nandi Betta path to Tipu Sultan's summer retreat, built for "
                        "people who want a sunrise and a view without a five-hour day on their legs.",
            long_description=(
                "This is the one we send first-timers, families and anyone coming back from a break in training. The "
                "route is a maintained stone stairway with handrails on the exposed sections, and there is a road to "
                "the top if anyone needs to bail out."
                "|| It is still an early start and still 1,200 steps, so it is not nothing. But you can be at the top "
                "for sunrise and back in Bengaluru before most people have had breakfast."
                "|| The summit has the summer palace, Tipu's Drop, a working temple and a cafe, which makes it a good "
                "place to actually sit for an hour rather than turn straight around."),
            price=649, difficulty="Easy, stepped path throughout", difficulty_band="Easy",
            duration="2.5 hours", distance="6 km round trip", altitude="1,478 m",
            group_size="8 - 20 trekkers",
            starting_point="Nandi Hills base, Sultanpet gate", ending_point="Tipu's summer palace, summit",
            best_season="All year, best from October to February",
            how_to_reach="Nandi Hills is 60 km from Bengaluru off NH44, about an hour by road. The stepped trail "
                         "starts near the Sultanpet gate at the base, separate from the vehicle road to the top.",
            highlights="Sunrise over the plateau; Tipu Sultan's summer palace; the Bhoga Nandeeshwara temple at the "
                       "base; Tipu's Drop viewpoint; paragliders launching on clear mornings; a summit cafe",
            things_to_carry="Any comfortable walking shoes; 1.5 litres of water; a light jacket for the summit wind; "
                            "sunscreen; a camera if you care about the sunrise",
            inclusions="Entry fee at the gate; lead guide and sweep guide; a guided walk of the summit ruins; "
                       "first-aid support; waste bags",
            exclusions="Transport from Bengaluru; breakfast at the summit cafe; personal gear",
            safety_info="The steps are well maintained but get slippery in the early morning dew, so take the descent "
                        "at a sensible pace. The summit edges near Tipu's Drop are unfenced in places and people take "
                        "risks there for photographs. Stay back from the drop.",
            permit_info="No trekking permit is needed. There is a standard entry fee at the gate, included in your "
                        "booking, and the hill has fixed opening hours enforced by the horticulture department.",
            itinerary=json.dumps([
                {"when": "4:30 am", "title": "Leave Bengaluru", "text": "Pickup from a central point and a straight run up NH44."},
                {"when": "5:45 am", "title": "Base gate", "text": "Entry formalities at Sultanpet and a short briefing at the foot of the steps."},
                {"when": "6:00 am", "title": "Climb the steps", "text": "Roughly 1,200 stone steps at an easy pace, with two rest points on the way."},
                {"when": "6:45 am", "title": "Sunrise at the top", "text": "Find a spot on the eastern edge before the crowd arrives from the road."},
                {"when": "7:30 am", "title": "Walk the summit", "text": "Summer palace, temple and Tipu's Drop, with the history behind each."},
                {"when": "9:30 am", "title": "Back in the city", "text": "Down the same steps and home before the day starts."},
            ]),
            faqs=json.dumps([
                {"q": "Can children do this?", "a": "Yes. Kids from about seven upwards manage the steps fine at a slow pace, and the road option exists if anyone tires."},
                {"q": "Is it very crowded?", "a": "The summit gets busy once the road traffic arrives around 7am. Climbing the steps early puts you up there well before that."},
                {"q": "What if I cannot finish the steps?", "a": "Tell the sweep guide. The vehicle road runs parallel and we can get you to the top or the base without drama."},
                {"q": "Is this enough training for the harder treks?", "a": "It is a good start. Do this comfortably, then Skandagiri or Kudremukh, and then think about Kumara Parvatha."},
            ]),
            gallery=json.dumps(PHOTOS["nandi-hills-sunrise"]["gallery"]),
            image_url=PHOTOS["nandi-hills-sunrise"]["local"], fallback_image=PHOTOS["nandi-hills-sunrise"]["remote"],
            rating=4.5, reviews_count=389,
        ),
    ]
    db.session.add_all(treks)
    db.session.commit()
    print(f"[DB] Seeded {len(treks)} treks.")


TREK_CODES = {
    "kudremukh": "KUD",
    "kumara-parvatha": "KPV",
    "savandurga": "SAV",
    "skandagiri": "SKN",
    "kodachadri": "KOD",
    "nandi-hills-sunrise": "NAN",
}


def generate_order_ref(cart_items):
    if cart_items:
        first = cart_items[0]
        code = TREK_CODES.get(first.trek_slug) or (first.trek_slug or "TRK")[:3].upper()
        distinct_treks = {c.trek_slug for c in cart_items}
        if len(distinct_treks) > 1:
            code = f"{code}+{len(distinct_treks) - 1}"
        try:
            date_part = datetime.strptime(first.trek_date, "%Y-%m-%d").strftime("%d%b").upper()
        except (ValueError, TypeError):
            date_part = ""
    else:
        code, date_part = "TRK", ""

    parts = ["PEAK", code] + ([date_part] if date_part else [])
    for _ in range(20):
        candidate = "-".join(parts + [uuid.uuid4().hex[:4].upper()])
        if not Order.query.filter_by(order_ref=candidate).first():
            return candidate
    return "-".join(parts + [uuid.uuid4().hex[:10].upper()])

CURRENT_PRICES = {
    "kudremukh": 2449,
    "kumara-parvatha": 2749,
    "savandurga": 849,
    "skandagiri": 1049,
    "kodachadri": 2349,
    "nandi-hills-sunrise": 649,
}


def sync_prices():
    changed = 0
    for slug, price in CURRENT_PRICES.items():
        trek = Trek.query.filter_by(slug=slug).first()
        if trek and trek.price != price:
            trek.price = price
            changed += 1
        if trek:
            for item in CartItem.query.filter_by(trek_id=trek.id).all():
                item.price = price
    if changed:
        db.session.commit()
        print(f"[DB] Updated pricing on {changed} trek(s).")
    else:
        db.session.commit()


def sync_photos():
    changed = 0
    for slug, shots in PHOTOS.items():
        trek = Trek.query.filter_by(slug=slug).first()
        if not trek:
            continue
        gallery = json.dumps(shots["gallery"])
        if (trek.gallery != gallery or trek.image_url != shots["local"]
                or trek.fallback_image != shots["remote"]):
            trek.gallery = gallery
            trek.image_url = shots["local"]
            trek.fallback_image = shots["remote"]
            changed += 1
    if changed:
        db.session.commit()
        print(f"[DB] Refreshed photographs on {changed} trek(s).")


def prepare_database():
    inspector = sa_inspect(db.engine)

    if "trek" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("trek")}
        if not {"slug", "itinerary", "state", "district"}.issubset(columns):
            print("[DB] Old schema found in peak.db. Rebuilding tables.")
            db.drop_all()

    db.create_all()

    inspector = sa_inspect(db.engine)
    if "enquiry" in inspector.get_table_names():
        have = {c["name"] for c in inspector.get_columns("enquiry")}
        for name, ddl in [("phone", "VARCHAR(30) DEFAULT ''"),
                          ("emailed", "BOOLEAN DEFAULT 0")]:
            if name not in have:
                db.session.execute(db.text(f"ALTER TABLE enquiry ADD COLUMN {name} {ddl}"))
                print(f"[DB] Added enquiry.{name}.")
        db.session.commit()

    if Trek.query.count() == 0:
        seed_treks()
    else:
        sync_prices()
        sync_photos()


if __name__ == "__main__":
    with app.app_context():
        prepare_database()
    app.run(debug=True)