from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    """Current wall-clock time in Bengaluru, as a naive datetime so it
    compares and formats the same way the rest of the app already expects."""
    return datetime.now(IST).replace(tzinfo=None)


def today_ist():
    return now_ist().date()

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

