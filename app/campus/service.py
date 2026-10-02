"""Helpers other modules use to notify users, audit admin actions and read
system settings."""

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.campus.models import ActivityLog, Notification, SystemSettings


def notify(
    db: Session,
    profile_ids: Iterable[int],
    title: str,
    body: str,
    type: str = "announcement",
    reference_id: Optional[str] = None,
    action_label: Optional[str] = None,
) -> None:
    """Adds notifications to the session; the caller commits."""
    for profile_id in set(profile_ids):
        db.add(
            Notification(
                profile_id=profile_id,
                title=title,
                body=body,
                type=type,
                reference_id=reference_id,
                action_label=action_label,
            )
        )


def log_activity(
    db: Session,
    title: str,
    description: str = "",
    actor_name: Optional[str] = None,
    severity: str = "info",
    category: Optional[str] = None,
) -> None:
    """Adds an audit entry to the session; the caller commits."""
    db.add(
        ActivityLog(
            title=title,
            description=description,
            actor_name=actor_name,
            severity=severity,
            category=category,
        )
    )


def get_settings(db: Session) -> SystemSettings:
    settings = db.get(SystemSettings, 1)
    if settings is None:
        settings = SystemSettings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings
