from datetime import datetime

from anyio import from_thread
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.common.deps import require_role
from app.auth.models import Role, Profile
from app.courses.models import Course
from app.classes import models, schemas
from app.participation.models import Question
from app.signaling.connection_manager import manager

router = APIRouter(prefix="/classes", tags=["classes"])


@router.post("", response_model=schemas.ClassSessionOut)
def start_session(
    payload: schemas.ClassSessionCreate,
    db: Session = Depends(get_db),
    lecturer: Profile = Depends(require_role(Role.lecturer)),
):
    course = db.query(Course).filter(Course.id == payload.course_id).first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    session = models.ClassSession(
        course_id=payload.course_id,
        lecturer_id=lecturer.id,
        started_at=datetime.utcnow(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/end", response_model=schemas.ClassSessionOut)
def end_session(
    session_id: int,
    db: Session = Depends(get_db),
    lecturer: Profile = Depends(require_role(Role.lecturer)),
):
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.lecturer_id != lecturer.id:
        raise HTTPException(status_code=403, detail="You do not own this session")
    if session.ended_at is not None:
        raise HTTPException(status_code=400, detail="Session already ended")

    session.ended_at = datetime.utcnow()
    db.query(Question).filter(
        Question.session_id == session_id, Question.is_open == True
    ).update({"is_open": False})
    db.commit()
    db.refresh(session)

    from_thread.run(manager.close_room, session_id, {"type": "session_ended"})
    return session