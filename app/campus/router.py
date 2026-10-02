from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.auth.models import Profile, Role
from app.campus import models, schemas
from app.campus.service import get_settings, log_activity
from app.common.deps import get_current_user, require_role
from app.common.pagination import Page, PageParams
from app.common.timeutils import to_naive_utc
from app.courses.models import Course
from app.database import get_db
from app.reports.analytics import course_stats, finished_sessions, overall_rate

router = APIRouter(tags=["campus"])


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def _notification_out(n: models.Notification) -> schemas.NotificationOut:
    return schemas.NotificationOut(
        id=n.id,
        user_id=n.profile_id,
        title=n.title,
        body=n.body,
        type=n.type,
        reference_id=n.reference_id,
        action_label=n.action_label,
        is_read=n.is_read,
        created_at=n.created_at,
    )


@router.get("/notifications", response_model=Page[schemas.NotificationOut])
def list_notifications(
    unread_only: bool = False,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    query = db.query(models.Notification).filter(models.Notification.profile_id == user.id)
    if unread_only:
        query = query.filter(models.Notification.is_read == False)  # noqa: E712
    query = query.order_by(models.Notification.id.desc())
    total = query.count()
    items = [_notification_out(n) for n in query.offset(params.offset).limit(params.page_size).all()]
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.post("/notifications/read-all", status_code=204)
def read_all_notifications(db: Session = Depends(get_db), user: Profile = Depends(get_current_user)):
    db.query(models.Notification).filter(
        models.Notification.profile_id == user.id, models.Notification.is_read == False  # noqa: E712
    ).update({"is_read": True})
    db.commit()
    return Response(status_code=204)


@router.post("/notifications/{notification_id}/read", response_model=schemas.NotificationOut)
def read_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    n = db.get(models.Notification, notification_id)
    if n is None or n.profile_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    db.commit()
    db.refresh(n)
    return _notification_out(n)


# ---------------------------------------------------------------------------
# Admin activity feed
# ---------------------------------------------------------------------------


@router.get("/admin/activity", response_model=list[schemas.ActivityOut])
def recent_activity(
    limit: int = 20,
    db: Session = Depends(get_db),
    _admin: Profile = Depends(require_role(Role.admin)),
):
    rows = (
        db.query(models.ActivityLog)
        .order_by(models.ActivityLog.id.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return [
        schemas.ActivityOut(
            id=r.id,
            title=r.title,
            description=r.description,
            actor_name=r.actor_name,
            severity=r.severity,
            category=r.category,
            timestamp=r.created_at,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Academic terms
# ---------------------------------------------------------------------------


def _term_out(db: Session, term: models.AcademicTerm) -> schemas.AcademicTermOut:
    sessions = finished_sessions(db, since=term.start_date, until=term.end_date)
    return schemas.AcademicTermOut(
        id=term.id,
        name=term.name,
        code=term.code,
        academic_year=term.academic_year,
        start_date=term.start_date,
        end_date=term.end_date,
        status=term.status,
        term_type=term.term_type,
        teaching_days=term.teaching_days,
        enrollment_open=term.enrollment_open,
        add_drop_deadline=term.add_drop_deadline,
        notes=term.notes,
        enrolled_students=db.query(Profile)
        .filter(Profile.role == Role.student, Profile.is_active == True)  # noqa: E712
        .count(),
        course_count=db.query(Course).filter(Course.is_archived == False).count(),  # noqa: E712
        average_attendance=overall_rate(course_stats(db, sessions).values()),
    )


def _apply_term(db: Session, term: models.AcademicTerm, payload: schemas.AcademicTermIn) -> None:
    start, end = to_naive_utc(payload.start_date), to_naive_utc(payload.end_date)
    if end <= start:
        raise HTTPException(status_code=400, detail="The term must end after it starts")
    duplicate = db.query(models.AcademicTerm).filter(
        models.AcademicTerm.code == payload.code, models.AcademicTerm.id != (term.id or -1)
    ).first()
    if duplicate:
        raise HTTPException(status_code=400, detail="A term with this code already exists")
    term.name = payload.name
    term.code = payload.code
    term.academic_year = payload.academic_year
    term.start_date = start
    term.end_date = end
    term.status = payload.status
    term.term_type = payload.term_type
    term.teaching_days = payload.teaching_days
    term.enrollment_open = payload.enrollment_open
    term.add_drop_deadline = to_naive_utc(payload.add_drop_deadline)
    term.notes = payload.notes
    if payload.status == "active":
        # Only one active term at a time.
        db.query(models.AcademicTerm).filter(
            models.AcademicTerm.status == "active", models.AcademicTerm.id != (term.id or -1)
        ).update({"status": "archived"})


@router.get("/academic-terms", response_model=list[schemas.AcademicTermOut])
def list_terms(db: Session = Depends(get_db), _user: Profile = Depends(get_current_user)):
    terms = db.query(models.AcademicTerm).order_by(models.AcademicTerm.start_date.desc()).all()
    return [_term_out(db, t) for t in terms]


@router.post("/academic-terms", response_model=schemas.AcademicTermOut, status_code=201)
def create_term(
    payload: schemas.AcademicTermIn,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    term = models.AcademicTerm()
    _apply_term(db, term, payload)
    db.add(term)
    log_activity(db, "Academic term created", payload.name, admin.full_name, "success", "system")
    db.commit()
    db.refresh(term)
    return _term_out(db, term)


@router.put("/academic-terms/{term_id}", response_model=schemas.AcademicTermOut)
def update_term(
    term_id: int,
    payload: schemas.AcademicTermIn,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    term = db.get(models.AcademicTerm, term_id)
    if term is None:
        raise HTTPException(status_code=404, detail="Academic term not found")
    _apply_term(db, term, payload)
    log_activity(db, "Academic term updated", payload.name, admin.full_name, "info", "system")
    db.commit()
    db.refresh(term)
    return _term_out(db, term)


# ---------------------------------------------------------------------------
# System settings
# ---------------------------------------------------------------------------


def _settings_out(s: models.SystemSettings) -> schemas.SystemSettingsOut:
    return schemas.SystemSettingsOut(
        late_threshold_minutes=s.late_threshold_minutes,
        auto_join_leave_recording=s.auto_join_leave_recording,
        participation_weight=s.participation_weight,
        strict_geofencing=s.strict_geofencing,
        session_timeout_minutes=s.session_timeout_minutes,
        enforce_sso=s.enforce_sso,
        minimum_attendance=s.minimum_attendance,
        cluster_version="smart-classroom-api",
        last_synced_at=s.updated_at,
    )


@router.get("/settings/system", response_model=schemas.SystemSettingsOut)
def read_settings(db: Session = Depends(get_db), _user: Profile = Depends(get_current_user)):
    return _settings_out(get_settings(db))


@router.put("/settings/system", response_model=schemas.SystemSettingsOut)
def update_settings(
    payload: schemas.SystemSettingsIn,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    settings = get_settings(db)
    for field, value in payload.model_dump().items():
        setattr(settings, field, value)
    settings.updated_at = datetime.utcnow()
    log_activity(db, "System settings updated", "", admin.full_name, "warning", "system")
    db.commit()
    db.refresh(settings)
    return _settings_out(settings)
