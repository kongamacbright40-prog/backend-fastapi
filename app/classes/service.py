from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.models import Profile, Role
from app.classes import models, schemas
from app.courses.service import can_teach, course_students, is_enrolled, student_course_ids
from app.signaling.connection_manager import manager

# A class without a planned duration is assumed to last this long.
DEFAULT_CLASS_LENGTH = timedelta(hours=2)
# How long past its expected end a class may stay open before it is closed.
STALE_GRACE = timedelta(hours=1)
# A live class everyone has left (e.g. the lecturer closed the tab without
# tapping "End class") is ended after this long.
ABANDONED_AFTER = timedelta(minutes=15)


def _last_left(db: Session, session_id: int):
    """When the last person left the class, or None if unknown / someone is
    still in it. Uses the live room first, then attendance records (after a
    server restart the room is gone)."""
    from sqlalchemy import func

    from app.attendance.models import AttendanceRecord

    if session_id in manager.emptied_at:
        return manager.emptied_at[session_id]
    still_in, last = (
        db.query(
            func.count(AttendanceRecord.id).filter(AttendanceRecord.left_at.is_(None)),
            func.max(AttendanceRecord.left_at),
        )
        .filter(AttendanceRecord.session_id == session_id, AttendanceRecord.joined_at.isnot(None))
        .one()
    )
    return last if still_in == 0 else None


def close_stale_sessions(db: Session) -> int:
    """Ends live classes nobody will end any more, so they stop being reported
    as live:

    * everyone left more than ABANDONED_AFTER ago (ended when the last left);
    * or long after their expected end (duration, or DEFAULT_CLASS_LENGTH, plus
      STALE_GRACE).

    Classes with someone still connected are left alone."""
    from app.participation.models import Question

    now = datetime.utcnow()
    live = (
        db.query(models.ClassSession)
        .filter(models.ClassSession.started_at.isnot(None), models.ClassSession.ended_at.is_(None))
        .all()
    )
    closed = 0
    for session in live:
        if manager.peers(session.id):
            continue
        last_left = _last_left(db, session.id)
        length = (
            timedelta(minutes=session.duration_minutes) if session.duration_minutes else DEFAULT_CLASS_LENGTH
        )
        expected_end = session.started_at + length
        if last_left is not None and now - last_left >= ABANDONED_AFTER:
            session.ended_at = max(last_left, session.started_at)
        elif now >= expected_end + STALE_GRACE:
            session.ended_at = expected_end
        else:
            continue
        manager.emptied_at.pop(session.id, None)
        db.query(Question).filter(
            Question.session_id == session.id, Question.is_open == True  # noqa: E712
        ).update({"is_open": False})
        closed += 1
    if closed:
        db.commit()
    return closed


def session_status(session: models.ClassSession) -> str:
    if session.ended_at is not None:
        return "completed"
    if session.started_at is not None:
        return "live"
    return "scheduled"


def session_out(db: Session, session: models.ClassSession) -> schemas.ClassSessionOut:
    return schemas.ClassSessionOut(
        id=session.id,
        course_id=session.course_id,
        lecturer_id=session.lecturer_id,
        title=session.title,
        scheduled_start=session.scheduled_start,
        duration_minutes=session.duration_minutes,
        started_at=session.started_at,
        ended_at=session.ended_at,
        status=session_status(session),
        course=schemas.CourseSummary.model_validate(session.course) if session.course else None,
        lecturer=schemas.LecturerSummary.model_validate(session.lecturer) if session.lecturer else None,
        participant_count=len(manager.peers(session.id)),
        expected_count=len(course_students(db, session.course)) if session.course else 0,
    )


def get_session_or_404(db: Session, session_id: int) -> models.ClassSession:
    session = db.get(models.ClassSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def can_view(db: Session, session: models.ClassSession, user: Profile) -> bool:
    if user.role == Role.admin:
        return True
    if user.role == Role.lecturer:
        return session.lecturer_id == user.id or can_teach(session.course, user)
    return is_enrolled(db, session.course, user)


def ensure_can_view(db: Session, session: models.ClassSession, user: Profile) -> None:
    if not can_view(db, session, user):
        raise HTTPException(status_code=403, detail="You are not part of this class")


def visible_sessions_query(db: Session, user: Profile):
    query = db.query(models.ClassSession)
    if user.role == Role.lecturer:
        query = query.filter(models.ClassSession.lecturer_id == user.id)
    elif user.role == Role.student:
        ids = student_course_ids(db, user)
        query = query.filter(models.ClassSession.course_id.in_(ids or {-1}))
    return query
