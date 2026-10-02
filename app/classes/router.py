from datetime import datetime, timedelta
from typing import Optional

from anyio import from_thread
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.attendance.models import AttendanceRecord
from app.auth.models import Profile, Role
from app.campus.service import notify
from app.classes import models, schemas
from app.classes.service import (
    close_stale_sessions,
    ensure_can_view,
    get_session_or_404,
    session_out,
    visible_sessions_query,
)
from app.common.deps import get_current_user, require_role
from app.common.pagination import Page, PageParams
from app.common.timeutils import to_naive_utc
from app.courses.models import Course
from app.courses.service import can_teach, course_students
from app.database import get_db
from app.participation.models import Question
from app.signaling.connection_manager import manager

router = APIRouter(prefix="/classes", tags=["classes"])


def _teachable_course(db: Session, course_id: int, lecturer: Profile) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.is_archived:
        raise HTTPException(status_code=404, detail="Course not found")
    if not can_teach(course, lecturer):
        raise HTTPException(status_code=403, detail="You do not teach this course")
    return course


def _owned_session(db: Session, session_id: int, lecturer: Profile) -> models.ClassSession:
    session = get_session_or_404(db, session_id)
    if session.lecturer_id != lecturer.id:
        raise HTTPException(status_code=403, detail="You do not own this session")
    return session


def _announce_start(db: Session, session: models.ClassSession) -> None:
    course = session.course
    notify(
        db,
        [s.id for s in course_students(db, course)],
        f"{course.code} is live",
        f"{session.title or course.title} has started. Join now to be marked present.",
        type="class_reminder",
        reference_id=str(session.id),
        action_label="Join Now",
    )


@router.post("", response_model=schemas.ClassSessionOut)
def start_session(
    payload: schemas.ClassSessionCreate,
    db: Session = Depends(get_db),
    lecturer: Profile = Depends(require_role(Role.lecturer)),
):
    """Creates a class and starts it immediately."""
    course = _teachable_course(db, payload.course_id, lecturer)
    now = datetime.utcnow()
    session = models.ClassSession(
        course_id=course.id,
        lecturer_id=lecturer.id,
        title=payload.title,
        scheduled_start=now,
        duration_minutes=payload.duration_minutes,
        started_at=now,
    )
    db.add(session)
    db.flush()
    _announce_start(db, session)
    db.commit()
    db.refresh(session)
    return session_out(db, session)


@router.post("/schedule", response_model=schemas.ClassSessionOut, status_code=201)
def schedule_session(
    payload: schemas.ClassSessionSchedule,
    db: Session = Depends(get_db),
    lecturer: Profile = Depends(require_role(Role.lecturer)),
):
    course = _teachable_course(db, payload.course_id, lecturer)
    start = to_naive_utc(payload.scheduled_start)
    if start < datetime.utcnow() - timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="The class must start in the future")
    session = models.ClassSession(
        course_id=course.id,
        lecturer_id=lecturer.id,
        title=payload.title,
        scheduled_start=start,
        duration_minutes=payload.duration_minutes,
    )
    db.add(session)
    db.flush()
    notify(
        db,
        [s.id for s in course_students(db, course)],
        f"New class for {course.code}",
        f"{payload.title or course.title} is scheduled for {start:%Y-%m-%d %H:%M} UTC.",
        type="class_reminder",
        reference_id=str(session.id),
    )
    db.commit()
    db.refresh(session)
    return session_out(db, session)


@router.get("", response_model=Page[schemas.ClassSessionOut])
def list_sessions(
    course_id: Optional[int] = None,
    live_only: bool = False,
    start_from: Optional[datetime] = Query(default=None, alias="from"),
    start_to: Optional[datetime] = Query(default=None, alias="to"),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    """Classes visible to the caller: admins see all, lecturers their own,
    students those of their courses."""
    close_stale_sessions(db)
    query = visible_sessions_query(db, user)
    if course_id is not None:
        query = query.filter(models.ClassSession.course_id == course_id)
    if live_only:
        query = query.filter(
            models.ClassSession.started_at.isnot(None), models.ClassSession.ended_at.is_(None)
        )
    when = func.coalesce(models.ClassSession.scheduled_start, models.ClassSession.started_at)
    if start_from is not None:
        query = query.filter(
            (when >= to_naive_utc(start_from))
            | (models.ClassSession.started_at.isnot(None) & models.ClassSession.ended_at.is_(None))
        )
    if start_to is not None:
        query = query.filter(when <= to_naive_utc(start_to))
    query = query.order_by(when.desc(), models.ClassSession.id.desc())

    total = query.count()
    items = [session_out(db, s) for s in query.offset(params.offset).limit(params.page_size).all()]
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.get("/{session_id}", response_model=schemas.ClassSessionOut)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    session = get_session_or_404(db, session_id)
    ensure_can_view(db, session, user)
    close_stale_sessions(db)
    return session_out(db, session)


@router.post("/{session_id}/start", response_model=schemas.ClassSessionOut)
def start_scheduled_session(
    session_id: int,
    db: Session = Depends(get_db),
    lecturer: Profile = Depends(require_role(Role.lecturer)),
):
    session = _owned_session(db, session_id, lecturer)
    if session.ended_at is not None:
        raise HTTPException(status_code=400, detail="Session already ended")
    if session.started_at is None:
        session.started_at = datetime.utcnow()
        _announce_start(db, session)
        db.commit()
        db.refresh(session)
    return session_out(db, session)


@router.post("/{session_id}/end", response_model=schemas.ClassSessionOut)
def end_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_role(Role.lecturer, Role.admin)),
):
    """The class's lecturer ends it; admins can end any class (e.g. one left
    running by mistake)."""
    session = get_session_or_404(db, session_id) if user.role == Role.admin else _owned_session(db, session_id, user)
    if session.ended_at is not None:
        raise HTTPException(status_code=400, detail="Session already ended")

    now = datetime.utcnow()
    if session.started_at is None:
        session.started_at = now
    session.ended_at = now
    db.query(Question).filter(
        Question.session_id == session_id, Question.is_open == True  # noqa: E712
    ).update({"is_open": False})
    db.commit()
    db.refresh(session)

    from_thread.run(manager.close_room, session_id, {"type": "session_ended"})
    return session_out(db, session)


# ---------------------------------------------------------------------------
# Live participants & raised hands
# ---------------------------------------------------------------------------


@router.get("/{session_id}/participants", response_model=list[schemas.ParticipantOut])
def list_participants(
    session_id: int,
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    """People currently connected to the class (signaling socket)."""
    session = get_session_or_404(db, session_id)
    ensure_can_view(db, session, user)
    peer_ids = manager.peers(session_id)
    if not peer_ids:
        return []
    profiles = {p.id: p for p in db.query(Profile).filter(Profile.id.in_(peer_ids)).all()}
    joined = {
        r.profile_id: r.joined_at
        for r in db.query(AttendanceRecord)
        .filter(AttendanceRecord.session_id == session_id, AttendanceRecord.profile_id.in_(peer_ids))
        .all()
    }
    now = datetime.utcnow()
    return [
        schemas.ParticipantOut(
            user_id=pid,
            name=profiles[pid].full_name,
            role=profiles[pid].role,
            joined_at=joined.get(pid) or now,
            is_hand_raised=manager.hand_raised(session_id, pid),
        )
        for pid in peer_ids
        if pid in profiles
    ]


@router.put("/{session_id}/hand", response_model=list[schemas.ParticipantOut])
def set_hand(
    session_id: int,
    payload: schemas.HandUpdate,
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    session = get_session_or_404(db, session_id)
    ensure_can_view(db, session, user)
    if user.id not in manager.peers(session_id):
        raise HTTPException(status_code=400, detail="Join the class first")
    manager.set_hand(session_id, user.id, payload.raised)
    return list_participants(session_id, db, user)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


def _message_out(message: models.ChatMessage) -> schemas.ChatMessageOut:
    return schemas.ChatMessageOut(
        id=message.id,
        session_id=message.session_id,
        sender_id=message.profile_id,
        sender_name=message.profile.full_name,
        sender_role=message.profile.role,
        message=message.message,
        is_question=message.is_question,
        created_at=message.created_at,
    )


@router.get("/{session_id}/messages", response_model=list[schemas.ChatMessageOut])
def list_messages(
    session_id: int,
    after_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    session = get_session_or_404(db, session_id)
    ensure_can_view(db, session, user)
    query = db.query(models.ChatMessage).filter(models.ChatMessage.session_id == session_id)
    if after_id is not None:
        query = query.filter(models.ChatMessage.id > after_id)
    return [_message_out(m) for m in query.order_by(models.ChatMessage.id).limit(500).all()]


@router.post("/{session_id}/messages", response_model=schemas.ChatMessageOut, status_code=201)
def send_message(
    session_id: int,
    payload: schemas.ChatMessageCreate,
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    session = get_session_or_404(db, session_id)
    ensure_can_view(db, session, user)
    if session.ended_at is not None:
        raise HTTPException(status_code=400, detail="This class has ended")
    message = models.ChatMessage(
        session_id=session_id,
        profile_id=user.id,
        message=payload.message.strip(),
        is_question=payload.is_question,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return _message_out(message)
