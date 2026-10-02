from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.attendance import models, schemas
from app.auth.models import Profile, Role
from app.campus.service import notify
from app.classes.models import ClassSession
from app.classes.schemas import CourseSummary, LecturerSummary
from app.classes.service import ensure_can_view, get_session_or_404
from app.common.deps import get_current_user, require_role
from app.common.pagination import Page, PageParams
from app.courses.models import Course
from app.courses.service import can_teach, course_students, student_course_ids
from app.database import get_db

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

    changed = record.status != payload.status
    record.status = payload.status
    if changed and profile.role == Role.student:
        notify(
            db,
            [profile.id],
            "Attendance updated",
            f"Your attendance for {session.course.code} was set to {payload.status.value}.",
            type="attendance_update",
            reference_id=str(session.id),
        )
    db.commit()
    db.refresh(record)
    return record


@router.get("/sessions/{session_id}", response_model=Page[schemas.AttendanceOut])
def list_attendance_for_session(
    session_id: int,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    session = get_session_or_404(db, session_id)
    ensure_can_view(db, session, user)
    query = db.query(models.AttendanceRecord).filter(models.AttendanceRecord.session_id == session_id)
    total = query.count()
    items = query.offset(params.offset).limit(params.page_size).all()

    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


def _brief(session: ClassSession) -> schemas.SessionBrief:
    return schemas.SessionBrief(
        id=session.id,
        title=session.title,
        started_at=session.started_at,
        ended_at=session.ended_at,
        duration_minutes=session.duration_minutes,
        course=CourseSummary.model_validate(session.course),
        lecturer=LecturerSummary.model_validate(session.lecturer) if session.lecturer else None,
    )


@router.get("/me", response_model=list[schemas.MyAttendanceOut])
def my_attendance(
    course_id: Optional[int] = None,
    db: Session = Depends(get_db),
    student: Profile = Depends(require_role(Role.student)),
):
    """Every finished class of the student's courses (absent when never
    joined) plus any class the student joined."""
    records = {
        r.session_id: r
        for r in db.query(models.AttendanceRecord)
        .filter(models.AttendanceRecord.profile_id == student.id)
        .all()
    }
    course_ids = student_course_ids(db, student)
    query = db.query(ClassSession).filter(
        ((ClassSession.course_id.in_(course_ids or {-1})) & ClassSession.ended_at.isnot(None))
        | ClassSession.id.in_(list(records) or [-1])
    )
    if course_id is not None:
        query = query.filter(ClassSession.course_id == course_id)

    result = []
    for session in query.order_by(ClassSession.started_at.desc(), ClassSession.id.desc()).all():
        record = records.get(session.id)
        result.append(
            schemas.MyAttendanceOut(
                session=_brief(session),
                record_id=record.id if record else None,
                status=record.status if record else models.AttendanceStatus.absent,
                joined_at=record.joined_at if record else None,
                left_at=record.left_at if record else None,
                duration_seconds=(record.duration_seconds or 0) if record else 0,
            )
        )
    return result


@router.get("/courses/{course_id}/summary", response_model=list[schemas.CourseAttendanceSummary])
def course_summary(
    course_id: int,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_role(Role.lecturer, Role.admin)),
):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if user.role == Role.lecturer and not can_teach(course, user):
        raise HTTPException(status_code=403, detail="You do not teach this course")

    session_ids = [
        s.id
        for s in db.query(ClassSession)
        .filter(ClassSession.course_id == course_id, ClassSession.ended_at.isnot(None))
        .all()
    ]
    total = len(session_ids)
    counts: dict[int, dict[str, int]] = {}
    if session_ids:
        for record in db.query(models.AttendanceRecord).filter(
            models.AttendanceRecord.session_id.in_(session_ids)
        ):
            entry = counts.setdefault(record.profile_id, {"present": 0, "partial": 0, "excused": 0})
            if record.status.value in entry:
                entry[record.status.value] += 1

    summaries = []
    for student in course_students(db, course):
        entry = counts.get(student.id, {"present": 0, "partial": 0, "excused": 0})
        summaries.append(
            schemas.CourseAttendanceSummary(
                profile=schemas.ProfileSummary.model_validate(student),
                total_sessions=total,
                present_count=entry["present"],
                late_count=entry["partial"],
                absent_count=max(total - entry["present"] - entry["partial"] - entry["excused"], 0),
                excused_count=entry["excused"],
            )
        )
    return summaries


@router.post("/sessions/{session_id}/appeals", response_model=schemas.AppealOut, status_code=201)
def submit_appeal(
    session_id: int,
    payload: schemas.AppealCreate,
    db: Session = Depends(get_db),
    student: Profile = Depends(require_role(Role.student)),
):
    session = get_session_or_404(db, session_id)
    ensure_can_view(db, session, student)
    pending = (
        db.query(models.AttendanceAppeal)
        .filter(
            models.AttendanceAppeal.session_id == session_id,
            models.AttendanceAppeal.profile_id == student.id,
            models.AttendanceAppeal.status == models.AppealStatus.pending,
        )
        .first()
    )
    if pending is not None:
        raise HTTPException(status_code=409, detail="You already have a pending appeal for this class")

    appeal = models.AttendanceAppeal(
        session_id=session_id,
        profile_id=student.id,
        reason=payload.reason.strip(),
        document_name=payload.document_name,
    )
    db.add(appeal)
    notify(
        db,
        [session.lecturer_id],
        "Attendance appeal",
        f"{student.full_name} appealed their attendance for {session.course.code}: {payload.reason.strip()[:120]}",
        type="attendance_update",
        reference_id=str(session.id),
    )
    db.commit()
    db.refresh(appeal)
    return appeal
