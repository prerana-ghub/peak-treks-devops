import json
from datetime import datetime

from database import db
from trek_dates import now_ist


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
    group_size = db.Column(db.String(50), nullable=False, default="6 â€“ 15 trekkers")

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


TREK_CODES = {
    "kudremukh": "KUD",
    "kumara-parvatha": "KPV",
    "savandurga": "SAV",
    "skandagiri": "SKN",
    "kodachadri": "KOD",
    "nandi-hills-sunrise": "NAN",
}


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



