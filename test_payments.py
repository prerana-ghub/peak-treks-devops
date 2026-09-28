import base64
import io
import uuid

import qrcode

UPI_PAYEE_VPA = "bookings@peak"
UPI_PAYEE_NAME = "PEAK Treks"


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

