from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.common.deps import require_role, get_current_user
from app.common.pagination import PageParams, Page
from app.auth.models import Role, Profile
from app.classes.models import ClassSession
from app.attendance import models, schemas

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.post("/sessions/{session_id}/mark", response_model=schemas.AttendanceOut)
def mark_attendance(
    session_id: int,
    payload: schemas.AttendanceMark,
    db: Session = Depends(get_db),
    lecturer: Profile = Depends(require_role(Role.lecturer)),
):
    session = db.query(ClassSession).filter(ClassSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.lecturer_id != lecturer.id:
        raise HTTPException(status_code=403, detail="You do not own this session")

    profile = db.query(Profile).filter(Profile.id == payload.profile_id).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    record = (
        db.query(models.AttendanceRecord)
        .filter(
            models.AttendanceRecord.session_id == session_id,
            models.AttendanceRecord.profile_id == payload.profile_id,
        )
        .first()
    )
    if record is None:
        record = models.AttendanceRecord(
            session_id=session_id,
            profile_id=payload.profile_id,
            role_at_time=profile.role,
        )
        db.add(record)

    record.status = payload.status
    db.commit()
    db.refresh(record)
    return record


@router.get("/sessions/{session_id}", response_model=Page[schemas.AttendanceOut])
def list_attendance_for_session(
    session_id: int,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _user: Profile = Depends(get_current_user),
):
    query = db.query(models.AttendanceRecord).filter(models.AttendanceRecord.session_id == session_id)
    total = query.count()
    items = query.offset(params.offset).limit(params.page_size).all()

    return Page(items=items, total=total, page=params.page, page_size=params.page_size)