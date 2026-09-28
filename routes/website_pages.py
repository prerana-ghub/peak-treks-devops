from flask import Blueprint, flash, redirect, render_template, request, session

from database import db

website_pages = Blueprint("website_pages", __name__)

CTA_PHOTO = "/static/cta-book-trek.jpg"
from helpers.user_authentication import current_user
from models import Trek, Order, Enquiry, Notification
from booking_emails import ENQUIRY_INBOX, SUPPORT_PHONE, send_enquiry_email, send_enquiry_ack
from helpers.user_notifications import notify

from models import Trek, Order
from trek_dates import get_available_dates
from data.trek_catalog import HERO_PHOTO, PHOTOS


@website_pages.route("/")
def index():
    featured = (Trek.query.order_by(Trek.featured.desc(), Trek.sort_order.asc())
                .limit(3).all())
    return render_template("home.html", nav="home", featured=featured,
                           hero_photo=HERO_PHOTO,
                           cta_photo=CTA_PHOTO,
                           cta_photo_fallback=PHOTOS["savandurga"]["remote"],
                           trek_count=Trek.query.count(),
                           trekker_count=900 + 7 * Order.query.filter_by(status="paid").count())


@website_pages.route("/treks")
def trek_list():
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "").strip()

    query = Trek.query

    if q:
        name_like = f"%{q}%"
        field_like = f"{q}%"

        query = query.filter(
        db.or_(
            Trek.name.ilike(name_like),
            Trek.location.ilike(field_like),
            Trek.district.ilike(field_like),
            Trek.state.ilike(field_like),
            Trek.region.ilike(field_like),
        )
    )

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


@website_pages.route("/trek/<slug>")
def trek_detail(slug):
    trek = Trek.query.filter_by(slug=slug).first()
    if not trek:
        return render_template("404.html"), 404

    related = (Trek.query.filter(Trek.id != trek.id)
               .order_by(Trek.featured.desc(), Trek.sort_order.asc()).limit(3).all())

    return render_template("trek_detail.html", nav="treks", trek=trek, related=related,
                           available_dates=get_available_dates(),
                           hero_focus=HERO_FOCUS.get(slug, "center center"))


# ---------------- static pages ----------------
@website_pages.route("/about")
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


@website_pages.route("/contact", methods=["GET", "POST"])
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



@website_pages.route("/notifications/open/<int:notif_id>")
def open_notification(notif_id):
    n = Notification.query.filter_by(id=notif_id, user_id=session.get("user_id")).first()
    if not n:
        return redirect("/")
    n.is_read = True
    db.session.commit()
    return redirect(n.link or request.referrer or "/")
