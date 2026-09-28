import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app, render_template

from database import db
from models import Trek
from trek_dates import pretty_date

ENQUIRY_INBOX = os.environ.get("ENQUIRY_INBOX", "")
SUPPORT_EMAIL = ENQUIRY_INBOX
SUPPORT_PHONE = "+91 80 4000 0000"


def deliver(msg, label, text_body=""):
    try:
        with smtplib.SMTP(
            current_app.config["MAIL_SERVER"],
            current_app.config["MAIL_PORT"],
            timeout=10,
        ) as smtp:
            if current_app.config.get("MAIL_USE_TLS"):
                smtp.starttls()

            username = current_app.config.get("MAIL_USERNAME")
            password = current_app.config.get("MAIL_PASSWORD")

            if username and password:
                smtp.login(username, password)

            smtp.send_message(msg)

        return True

    except Exception as exc:
        print(f"[EMAIL] {label} failed: {exc}")

        if text_body:
            print(text_body)

        return False


def send_enquiry_email(enquiry):
    sender = current_app.config["MAIL_SENDER"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"New enquiry from {enquiry.name}"
    msg["From"] = sender
    msg["To"] = ENQUIRY_INBOX

    text_body = f"""New enquiry from {enquiry.name}

Email: {enquiry.email}
Phone: {enquiry.phone or "Not provided"}

Message:
{enquiry.message}
"""

    html_body = render_template("email_enquiry.html", enquiry=enquiry)

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    return deliver(msg, "enquiry", text_body)


def send_enquiry_ack(enquiry):
    sender = current_app.config["MAIL_SENDER"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "We received your enquiry — PEAK Treks"
    msg["From"] = sender
    msg["To"] = enquiry.email

    text_body = f"""Hi {enquiry.name},

Thanks for reaching out to PEAK Treks.

We've received your enquiry and will get back to you soon.

For urgent questions:
Email: {SUPPORT_EMAIL}
Phone: {SUPPORT_PHONE}

— PEAK Treks
"""

    html_body = render_template(
        "email_enquiry_ack.html",
        enquiry=enquiry,
        support_phone=SUPPORT_PHONE,
    )

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    return deliver(msg, "enquiry acknowledgement", text_body)


def email_image_for(item):
    if (item.image_url or "").startswith("http"):
        return item.image_url

    trek = db.session.get(Trek, item.trek_id) if item.trek_id else None
    return trek.fallback_image if trek else ""


def meeting_point_for(item):
    trek = db.session.get(Trek, item.trek_id)
    return trek.ending_point if trek else ""


def send_receipt_email(order, payment):
    sender = current_app.config["MAIL_SENDER"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"PEAK Treks — Booking Confirmation #{order.id}"
    msg["From"] = sender
    msg["To"] = order.email

    lines = [
        f"Hi {order.name},",
        "",
        "Your PEAK Treks booking is confirmed.",
        "",
        f"Order ID: {order.id}",
        f"Payment ID: {payment.transaction_id}",
        f"Payment method: {payment.method}",
        "",
        "",
        "Treks:",
    ]

    for item in order.items():
        lines.extend(
            [
                f"- {item.trek_name} × {item.people}",
                f"  Meeting point: {meeting_point_for(item)}",
            ]
        )

    lines.extend(
        [
            "",
            f"Total paid: ₹{order.total:.2f}",
            "",
            f"Support: {SUPPORT_EMAIL}",
            f"Phone: {SUPPORT_PHONE}",
            "",
            "— PEAK Treks",
        ]
    )

    text_body = "\n".join(lines)

    html_body = render_template(
        "email_booking_confirmation.html",
        order=order,
        payment=payment,
        pretty_date=pretty_date,
        email_image_for=email_image_for,
        meeting_point_for=meeting_point_for,
        support_email=SUPPORT_EMAIL,
        support_phone=SUPPORT_PHONE,
    )

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    return deliver(msg, "receipt", text_body)
