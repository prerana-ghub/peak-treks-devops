GST_RATE = 0.05
BOOKING_FEE = 49
MIN_PEOPLE = 1
MAX_PEOPLE = 20


def calculate_bill(subtotal):
    gst = round(subtotal * GST_RATE)
    fee = BOOKING_FEE if subtotal > 0 else 0
    return subtotal, gst, fee, subtotal + gst + fee

