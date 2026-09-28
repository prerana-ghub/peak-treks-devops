from flask import session

from database import db
from models import Notification


def notify(user_id, title, message, kind="info", link=None):
    if not user_id:
        return
    db.session.add(Notification(
        user_id=user_id,
        title=title,
        message=message,
        kind=kind,
        link=link
    ))
    db.session.commit()


def get_unread_notif_count():
    if not session.get("user_id"):
        return 0
    return Notification.query.filter_by(
        user_id=session["user_id"],
        is_read=False
    ).count()


def get_recent_notifs(limit=8):
    if not session.get("user_id"):
        return []
    return (Notification.query
            .filter_by(user_id=session["user_id"])
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .all())