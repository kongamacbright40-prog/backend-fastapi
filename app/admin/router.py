from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.schemas import ProfileCreate
from app.auth.service import create_profile
from app.database import get_db
from app.common.deps import require_role
from app.common.pagination import PageParams, Page
from app.auth.models import Role, Profile
from app.courses.models import Department
from app.classes.models import ClassSession
from app.classes.schemas import ClassSessionOut
from app.attendance.models import AttendanceRecord, AttendanceStatus
from app.admin import schemas

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=Page[schemas.AdminUserOut])
def list_users(
    role: Optional[Role] = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _admin: Profile = Depends(require_role(Role.admin)),
):
    query = db.query(Profile)
    if role is not None:
        query = query.filter(Profile.role == role)
    query = query.order_by(Profile.id)

    total = query.count()
    items = query.offset(params.offset).limit(params.page_size).all()
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.patch("/users/{user_id}/department", response_model=schemas.AdminUserOut)
def assign_department(
    user_id: int,
    payload: schemas.AssignDepartment,
    db: Session = Depends(get_db),
    _admin: Profile = Depends(require_role(Role.admin)),
):
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    department = db.query(Department).filter(Department.id == payload.department_id).first()
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")

    user.department_id = payload.department_id
    db.commit()
    db.refresh(user)
    return user


@router.get("/sessions", response_model=Page[ClassSessionOut])
def list_sessions(
    live_only: bool = False,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _admin: Profile = Depends(require_role(Role.admin)),
):
    query = db.query(ClassSession)
    if live_only:
        query = query.filter(ClassSession.ended_at.is_(None))
    query = query.order_by(ClassSession.id.desc())

    total = query.count()
    items = query.offset(params.offset).limit(params.page_size).all()
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.get("/teaching-hours", response_model=Page[schemas.TeachingHoursRow])
def teaching_hours(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _admin: Profile = Depends(require_role(Role.admin)),
):
    finished = (
        db.query(ClassSession)
        .filter(ClassSession.started_at.isnot(None), ClassSession.ended_at.isnot(None))
        .all()
    )

    totals = {}
    for session in finished:
        seconds = (session.ended_at - session.started_at).total_seconds()
        entry = totals.setdefault(
            session.lecturer_id,
            {"name": session.lecturer.full_name, "count": 0, "seconds": 0.0},
        )
        entry["count"] += 1
        entry["seconds"] += seconds

    rows = [
        schemas.TeachingHoursRow(
            lecturer_id=lecturer_id,
            full_name=entry["name"],
            sessions_count=entry["count"],
            total_hours=round(entry["seconds"] / 3600, 2),
        )
        for lecturer_id, entry in sorted(totals.items())
    ]

    page_rows = rows[params.offset : params.offset + params.page_size]
    return Page(items=page_rows, total=len(rows), page=params.page, page_size=params.page_size)


@router.get("/attendance-hours", response_model=Page[schemas.AttendanceHoursRow])
def attendance_hours(
    role: Optional[Role] = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _admin: Profile = Depends(require_role(Role.admin)),
):
    query = (
        db.query(
            Profile,
            func.count(AttendanceRecord.id),
            func.coalesce(func.sum(AttendanceRecord.duration_seconds), 0),
        )
        .join(AttendanceRecord, AttendanceRecord.profile_id == Profile.id)
        .filter(AttendanceRecord.status != AttendanceStatus.absent)
        .group_by(Profile.id)
        .order_by(Profile.id)
    )
    if role is not None:
        query = query.filter(Profile.role == role)

    total = query.count()
    results = query.offset(params.offset).limit(params.page_size).all()

    items = [
        schemas.AttendanceHoursRow(
            profile_id=profile.id,
            full_name=profile.full_name,
            matricule_number=profile.matricule_number,
            role=profile.role,
            sessions_attended=count,
            total_hours=round(total_seconds / 3600, 2),
        )
        for profile, count, total_seconds in results
    ]
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)

@router.post("/users", response_model=schemas.AdminUserOut, status_code=201)
def create_user(
    payload: ProfileCreate,
    db: Session = Depends(get_db),
    _admin: Profile = Depends(require_role(Role.admin)),
):
    return create_profile(db, payload)
