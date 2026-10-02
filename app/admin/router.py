from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.auth.service import unusable_password_hash
from app.campus.service import log_activity
from app.database import get_db
from app.common.deps import require_role
from app.common.pagination import PageParams, Page
from app.auth.models import Role, Profile
from app.courses.models import Course, Department, Enrollment
from app.classes.models import ChatMessage, ClassSession
from app.classes.schemas import ClassSessionOut
from app.classes.service import close_stale_sessions, session_out
from app.attendance.models import AttendanceAppeal, AttendanceRecord, AttendanceStatus
from app.admin import schemas

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=Page[schemas.AdminUserOut])
def list_users(
    role: Optional[Role] = None,
    q: Optional[str] = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _admin: Profile = Depends(require_role(Role.admin)),
):
    query = db.query(Profile)
    if role is not None:
        query = query.filter(Profile.role == role)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            Profile.full_name.ilike(like) | Profile.email.ilike(like) | Profile.matricule_number.ilike(like)
        )
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
    log_activity(db, "Department assigned", f"{user.full_name} → {department.name}", _admin.full_name, "info", "users")
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
        close_stale_sessions(db)
        query = query.filter(ClassSession.started_at.isnot(None), ClassSession.ended_at.is_(None))
    query = query.order_by(ClassSession.id.desc())

    total = query.count()
    items = [session_out(db, s) for s in query.offset(params.offset).limit(params.page_size).all()]
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

def _get_user(db: Session, user_id: int) -> Profile:
    user = db.get(Profile, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _check_unique(db: Session, email: Optional[str], matricule: Optional[str], exclude_id: int = -1) -> None:
    if email and db.query(Profile).filter(func.lower(Profile.email) == email, Profile.id != exclude_id).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if matricule and db.query(Profile).filter(
        Profile.matricule_number == matricule, Profile.id != exclude_id
    ).first():
        raise HTTPException(status_code=400, detail="Matricule number already registered")


def _check_department(db: Session, department_id: Optional[int]) -> None:
    if department_id is not None and db.get(Department, department_id) is None:
        raise HTTPException(status_code=404, detail="Department not found")


@router.post("/users", response_model=schemas.AdminUserOut, status_code=201)
def create_user(
    payload: schemas.AdminUserCreate,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    matricule = (payload.matricule_number or "").strip() or None
    _check_unique(db, payload.email, matricule)
    _check_department(db, payload.department_id)
    user = Profile(
        full_name=payload.full_name.strip(),
        email=payload.email,
        phone_number=(payload.phone_number or "").strip() or None,
        matricule_number=matricule,
        role=payload.role,
        department_id=payload.department_id,
        hashed_password=hash_password(payload.password) if payload.password else unusable_password_hash(),
        pending_activation=payload.password is None,
    )
    db.add(user)
    log_activity(
        db,
        "User created",
        f"{user.full_name} ({payload.role.value})" + (" — pending activation" if payload.password is None else ""),
        admin.full_name,
        "success",
        "users",
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=schemas.AdminUserOut)
def update_user(
    user_id: int,
    payload: schemas.AdminUserUpdate,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    user = _get_user(db, user_id)
    data = payload.model_dump(exclude_unset=True)
    matricule = (data.get("matricule_number") or "").strip() or None if "matricule_number" in data else None
    _check_unique(db, data.get("email"), matricule, exclude_id=user.id)
    if "department_id" in data:
        _check_department(db, data["department_id"])
        user.department_id = data["department_id"]
    if data.get("full_name"):
        user.full_name = data["full_name"].strip()
    if data.get("email"):
        user.email = data["email"]
    if "phone_number" in data:
        user.phone_number = (data["phone_number"] or "").strip() or None
    if "matricule_number" in data:
        user.matricule_number = matricule
    log_activity(db, "User updated", user.full_name, admin.full_name, "info", "users")
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/status", response_model=schemas.AdminUserOut)
def set_user_status(
    user_id: int,
    payload: schemas.UserStatusUpdate,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    user = _get_user(db, user_id)
    if user.id == admin.id and not payload.is_active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    user.is_active = payload.is_active
    log_activity(
        db,
        "User activated" if payload.is_active else "User deactivated",
        user.full_name,
        admin.full_name,
        "info" if payload.is_active else "warning",
        "users",
    )
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    user = _get_user(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    has_history = (
        db.query(AttendanceRecord).filter(AttendanceRecord.profile_id == user.id).first()
        or db.query(ClassSession).filter(ClassSession.lecturer_id == user.id).first()
        or db.query(ChatMessage).filter(ChatMessage.profile_id == user.id).first()
        or db.query(AttendanceAppeal).filter(AttendanceAppeal.profile_id == user.id).first()
    )
    if has_history:
        raise HTTPException(
            status_code=409,
            detail="This user has class history; deactivate the account instead",
        )
    db.query(Enrollment).filter(Enrollment.profile_id == user.id).delete()
    db.query(Course).filter(Course.lecturer_id == user.id).update({"lecturer_id": None})
    from app.campus.models import Notification
    from app.auth.models import PasswordResetCode

    db.query(Notification).filter(Notification.profile_id == user.id).delete()
    db.query(PasswordResetCode).filter(PasswordResetCode.profile_id == user.id).delete()
    log_activity(db, "User deleted", f"{user.full_name} ({user.email})", admin.full_name, "critical", "users")
    db.delete(user)
    db.commit()
    return Response(status_code=204)
