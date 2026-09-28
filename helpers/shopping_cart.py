import uuid

from flask import session

from database import db
from models import CartItem
from booking_billing import MAX_PEOPLE


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
    """Claims the guest cart for the signed-in account and merges duplicate
    trek/date rows without exceeding the maximum number of people."""
    key = get_cart_key()

    for row in CartItem.query.filter_by(cart_key=key).all():
        row.user_id = user.id

    for row in CartItem.query.filter(
        CartItem.user_id == user.id,
        CartItem.cart_key != key
    ).all():
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

    return session["cart_key"]
