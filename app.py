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
from flask_wtf import CSRFProtect

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


app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///peak.db")
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

AUTH_PHOTO_SIGNIN = "/static/auth-signin.jpg"
AUTH_PHOTO_SIGNUP = "/static/auth-signup.jpg"
CTA_PHOTO = "/static/cta-book-trek.jpg"
ERROR_PHOTO = "/static/error-404.jpg"

GST_RATE = 0.05
BOOKING_FEE = 49
MIN_PEOPLE = 1
MAX_PEOPLE = 20

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

@app.route("/healthz")
def healthz():
   return "ok", 200


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
ENQUIRY_INBOX = os.environ.get("ENQUIRY_INBOX", "")

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

    return render_template("trek_list.html", nav="treks", treks=query.all(),
                           total=Trek.query.count(), q=q, sort=sort)


HERO_FOCUS = {}


@app.route("/trek/<slug>")
def trek_detail(slug):
    trek = Trek.query.filter_by(slug=slug).first()
    if not trek:
        return render_template("404.html"), 404

    related = (Trek.query.filter(Trek.id != trek.id)
               .order_by(Trek.featured.desc(), Trek.sort_order.asc()).limit(3).all())

    return render_template("trek_detail.html", nav="treks", trek=trek, related=related,
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

    return render_template("booking_confirmation.html", nav="cart", order=order,
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
    return render_template("my_bookings.html", nav="bookings", orders=orders, stats=stats)


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
        "local": "/static/kudremukh.jpg",
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
        "local": "/static/kumara-parvatha.jpg",
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
        "local": "/static/savandurga.png",
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
            if os.environ.get("RESET_DB") == "1":
                print("[DB] Old schema found. RESET_DB=1 is set, rebuilding tables.")
                db.drop_all()
            else:
                raise RuntimeError(
                    "Old database schema found. Refusing to drop tables. "
                    "Set RESET_DB=1 once if you really want to rebuild."
                )

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