from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from datetime import datetime
import uuid

from database import db
from models import CartItem, Order, OrderItem, Payment, Trek
from trek_dates import pretty_date, valid_trek_date
from booking_billing import MIN_PEOPLE, MAX_PEOPLE, calculate_bill
from test_payments import process_test_card_payment, process_test_upi_payment, generate_upi_qr_data_uri
from helpers.shopping_cart import get_cart_key, get_cart, get_cart_total
from helpers.user_authentication import login_required
from helpers.user_notifications import notify
from booking_emails import send_receipt_email
from data.trek_catalog import TREK_CODES

trek_booking = Blueprint("trek_booking", __name__)


def generate_order_ref(cart_items):
    if cart_items:
        first = cart_items[0]
        code = TREK_CODES.get(first.trek_slug) or (first.trek_slug or "TRK")[:3].upper()
        distinct_treks = {c.trek_slug for c in cart_items}
        if len(distinct_treks) > 1:
            code = f"{code}+{len(distinct_treks) - 1}"
        try:
            date_part = datetime.strptime(
                first.trek_date, "%Y-%m-%d"
            ).strftime("%d%b").upper()
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


@trek_booking.route("/cart/add", methods=["POST"])
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

    existing = CartItem.query.filter_by(
        cart_key=get_cart_key(), trek_id=trek.id, trek_date=trek_date
    ).first()

    if existing:
        existing.people = min(existing.people + people, MAX_PEOPLE)
        db.session.commit()
        flash(f"Updated {trek.name} to {existing.people} trekkers.", "success")
    else:
        db.session.add(CartItem(
            cart_key=get_cart_key(),
            user_id=session.get("user_id"),
            trek_id=trek.id,
            trek_slug=trek.slug,
            trek_name=trek.name,
            location=trek.location,
            image_url=trek.image_url,
            trek_date=trek_date,
            people=people,
            price=trek.price,
        ))
        db.session.commit()
        flash(f"{trek.name} added to your cart.", "success")
        notify(
            session.get("user_id"),
            "Added to cart",
            f"{trek.name} on {pretty_date(trek_date)}.",
            "info",
            link="/cart",
        )

    return redirect("/cart")


@trek_booking.route("/cart")
def cart_view():
    cart = get_cart()
    subtotal, gst, booking_fee, total = calculate_bill(get_cart_total())

    recent_orders = []
    if session.get("user_id"):
        recent_orders = (
            Order.query
            .filter_by(user_id=session["user_id"], status="paid")
            .order_by(Order.created_at.desc())
            .limit(3)
            .all()
        )

    return render_template(
        "cart.html",
        nav="cart",
        cart=cart,
        subtotal=subtotal,
        gst=gst,
        booking_fee=booking_fee,
        total=total,
        recent_orders=recent_orders,
    )


@trek_booking.route("/cart/update/<int:item_id>", methods=["POST"])
def cart_update(item_id):
    item = CartItem.query.filter_by(
        id=item_id, cart_key=get_cart_key()
    ).first()

    if item:
        people = request.form.get("people", type=int) or 1
        item.people = max(MIN_PEOPLE, min(people, MAX_PEOPLE))
        db.session.commit()
        flash(f"{item.trek_name} updated to {item.people} trekkers.", "success")

    return redirect("/cart")


@trek_booking.route("/cart/remove/<int:item_id>", methods=["POST"])
def cart_remove(item_id):
    item = CartItem.query.filter_by(
        id=item_id, cart_key=get_cart_key()
    ).first()

    if item:
        name = item.trek_name
        db.session.delete(item)
        db.session.commit()
        flash(f"{name} removed from your cart.", "info")

    return redirect("/cart")


@trek_booking.route("/checkout", methods=["GET", "POST"])
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
            order = Order(
                order_ref=generate_order_ref(cart),
                user_id=user.id,
                name=form["name"],
                email=form["email"],
                phone=form["phone"],
                subtotal=subtotal,
                gst=gst,
                booking_fee=booking_fee,
                total=total,
                status="pending"
            )
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
            db.session.add(OrderItem(
                order_id=order.id,
                trek_id=c.trek_id,
                trek_slug=c.trek_slug,
                trek_name=c.trek_name,
                location=c.location,
                image_url=c.image_url,
                trek_date=c.trek_date,
                people=c.people,
                price=c.price
            ))
        db.session.commit()

        if selected_method == "upi":
            upi_id = request.form.get("upi_id", "").strip()
            result = process_test_upi_payment(upi_id, total)
            method_label = "UPI"
        else:
            upi_id = None
            result = process_test_card_payment(
                request.form.get("card_number", ""),
                request.form.get("expiry", ""),
                request.form.get("cvv", ""),
                total
            )
            method_label = "Test card"

        payment = Payment(
            order_id=order.id,
            transaction_id=result.get("transaction_id") or f"FAIL-{uuid.uuid4().hex[:12].upper()}",
            payment_method=selected_method,
            method=method_label,
            upi_id=upi_id if selected_method == "upi" else None,
            amount=total,
            status="success" if result["success"] else "failed",
            gateway_message=result["message"]
        )
        db.session.add(payment)

        if result["success"]:
            order.status = "paid"
            db.session.commit()
            session.pop("pending_order_id", None)

            notify(
                user.id,
                "Booking confirmed",
                f"{order.order_ref} is paid. Details are in your email.",
                "success",
                link=f"/order/{order.id}/confirmation"
            )

            CartItem.query.filter_by(cart_key=get_cart_key()).delete()
            db.session.commit()

            send_receipt_email(order, payment)
            flash("Payment approved. Your booking is confirmed.", "success")
            return redirect(f"/order/{order.id}/confirmation")

        order.status = "failed"
        db.session.commit()
        notify(
            user.id,
            "Payment did not go through",
            f"{order.order_ref}: {result['message']}",
            "error",
            link=f"/order/{order.id}/confirmation"
        )
        flash(result["message"] + " Your cart is untouched, so you can try again.", "error")

    return render_template(
        "checkout.html",
        nav="cart",
        cart=cart,
        form=form,
        subtotal=subtotal,
        gst=gst,
        booking_fee=booking_fee,
        total=total,
        selected_method=selected_method,
        qr_data_uri=generate_upi_qr_data_uri(total)
    )

@trek_booking.route("/order/<int:order_id>/confirmation")
def order_confirmation(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return render_template("404.html"), 404

    if order.user_id and order.user_id != session.get("user_id"):
        flash("Sign in with the account that made this booking to see it.", "info")
        return redirect(url_for("user_authentication.signin", next=request.path))

    payment = order.latest_payment()
    if not payment:
        return render_template("404.html"), 404

    return render_template(
        "booking_confirmation.html",
        nav="cart",
        order=order,
        payment=payment,
        paid=(order.status == "paid")
    )


@trek_booking.route("/bookings")
@login_required
def bookings():
    orders = (
        Order.query
        .filter_by(user_id=session["user_id"])
        .order_by(Order.created_at.desc())
        .all()
    )

    paid = [o for o in orders if o.status == "paid"]
    stats = {
        "paid": len(paid),
        "people": sum(o.headcount() for o in paid),
        "spent": sum(o.total for o in paid),
        "failed": len([o for o in orders if o.status != "paid"]),
    }

    return render_template(
        "my_bookings.html",
        nav="bookings",
        orders=orders,
        stats=stats
    )


