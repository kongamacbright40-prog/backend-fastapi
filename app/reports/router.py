from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.models import Profile, Role
from app.campus.service import get_settings
from app.classes.models import ClassSession
from app.classes.service import close_stale_sessions
from app.common.deps import require_role
from app.courses.models import Course, Department
from app.courses.service import can_teach
from app.database import get_db
from app.reports import service
from app.reports.analytics import at_risk_students, course_stats, finished_sessions, overall_rate, weekly_trend
from app.reports.csv_export import build_attendance_csv
from app.reports.excel_export import build_attendance_xlsx
from app.reports.pdf_export import build_attendance_pdf

router = APIRouter(prefix="/reports", tags=["reports"])

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _report(report_id: str, title: str, type_: str, metrics: dict, trend=None, breakdown=None, scope_id=None):
    now = datetime.utcnow()
    return {
        "id": report_id,
        "title": title,
        "type": type_,
        "generated_at": _iso(now),
        "period_start": _iso(now - timedelta(weeks=8)),
        "period_end": _iso(now),
        "scope_id": scope_id,
        "metrics": {k: v for k, v in metrics.items() if v is not None},
        "trend": trend or [],
        "previous_trend": [],
        "breakdown": breakdown or [],
    }


def _course_breakdown(stats) -> list[dict]:
    rows = []
    for s in sorted(stats.values(), key=lambda s: s.course.code):
        rows.append(
            {
                "id": str(s.course.id),
                "label": s.course.code,
                "value": s.rate or 0.0,
                "subtitle": s.course.title,
                "meta": {
                    "type": "course",
                    "students": str(s.students),
                    "sessions": str(s.sessions),
                    "lecturer": s.course.lecturer.full_name if s.course.lecturer else "",
                },
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Summaries (JSON in the app's report shape)
# ---------------------------------------------------------------------------


@router.get("/overview")
def admin_overview(db: Session = Depends(get_db), _admin: Profile = Depends(require_role(Role.admin))):
    minimum = get_settings(db).minimum_attendance
    sessions = finished_sessions(db)
    stats = course_stats(db, sessions)
    week_ago = datetime.utcnow() - timedelta(days=7)
    students = db.query(Profile).filter(Profile.role == Role.student)
    close_stale_sessions(db)
    live = (
        db.query(ClassSession)
        .filter(ClassSession.started_at.isnot(None), ClassSession.ended_at.is_(None))
        .count()
    )
    return _report(
        "admin-dashboard",
        "Administration Dashboard",
        "institution",
        {
            "total_students": students.count(),
            "new_students": students.filter(Profile.created_at >= week_ago).count(),
            "total_staff": db.query(Profile).filter(Profile.role == Role.lecturer).count(),
            "active_classes": live,
            "sessions": len(sessions),
            "avg_attendance": overall_rate(stats.values()),
            "attendance_target": minimum,
            "at_risk": len(at_risk_students(stats.values(), minimum)),
        },
    )


@router.get("/lecturer")
def lecturer_report(
    course_id: Optional[int] = None,
    lecturer_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_role(Role.lecturer, Role.admin)),
):
    target_id = user.id if user.role == Role.lecturer else lecturer_id
    if target_id is None:
        raise HTTPException(status_code=400, detail="lecturer_id is required")
    courses = db.query(Course).filter(Course.lecturer_id == target_id)
    if course_id is not None:
        courses = courses.filter(Course.id == course_id)
    course_ids = [c.id for c in courses.all()]
    # Classes the lecturer taught also count when the course is unassigned.
    taught = {
        s.course_id for s in db.query(ClassSession).filter(ClassSession.lecturer_id == target_id).all()
    }
    if course_id is None:
        course_ids = list(set(course_ids) | taught)
    elif course_id in taught:
        course_ids = list(set(course_ids) | {course_id})

    minimum = get_settings(db).minimum_attendance
    sessions = finished_sessions(db, course_ids)
    stats = course_stats(db, sessions)
    scope = f"course-{course_id}" if course_id is not None else f"lecturer-{target_id}"
    return _report(
        scope,
        "Attendance report",
        "attendance",
        {
            "average_rate": overall_rate(stats.values()),
            "sessions": len(sessions),
            "students": sum(s.students for s in stats.values()),
            "at_risk": len(at_risk_students(stats.values(), minimum)),
            "target": minimum,
        },
        trend=weekly_trend(db, sessions),
        breakdown=_course_breakdown(stats),
        scope_id=str(course_id) if course_id is not None else None,
    )


@router.get("/institution")
def institution_report(
    department_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _admin: Profile = Depends(require_role(Role.admin)),
):
    courses = db.query(Course)
    if department_id is not None:
        courses = courses.filter(Course.department_id == department_id)
    course_ids = [c.id for c in courses.all()]
    minimum = get_settings(db).minimum_attendance
    sessions = finished_sessions(db, course_ids)
    stats = course_stats(db, sessions)

    faculties: dict[int, list] = {}
    for s in stats.values():
        faculty = s.course.department.faculty
        entry = faculties.setdefault(faculty.id, [faculty.name, 0, 0, set()])
        entry[1] += s.attended
        entry[2] += s.expected
        entry[3].update(s.per_student)
    faculty_rows = [
        {
            "id": f"faculty-{fid}",
            "label": name,
            "value": round(att / exp * 100, 1) if exp else 0.0,
            "subtitle": f"{len(students)} students",
            "meta": {"type": "faculty", "students": str(len(students))},
        }
        for fid, (name, att, exp, students) in sorted(faculties.items(), key=lambda kv: kv[1][0])
    ]
    scope = f"department-{department_id}" if department_id is not None else "institution"
    return _report(
        scope,
        "Institution attendance",
        "institution",
        {
            "overall_rate": overall_rate(stats.values()),
            "sessions": len(sessions),
            "at_risk": len(at_risk_students(stats.values(), minimum)),
            "target": minimum,
        },
        trend=weekly_trend(db, sessions),
        breakdown=faculty_rows + _course_breakdown(stats),
        scope_id=str(department_id) if department_id is not None else None,
    )


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


def _export_content(
    db: Session,
    user: Profile,
    session_id: Optional[int],
    course_id: Optional[int],
    lecturer_id: Optional[int],
    department_id: Optional[int],
    utc_offset_minutes: int = 0,
) -> tuple[str, list, str]:
    """Returns (title, sections, file stem) for the requested scope. Times are
    shown in the caller's clock (utc_offset_minutes, e.g. 60 for UTC+1)."""
    offset = timedelta(minutes=max(-840, min(840, utc_offset_minutes)))
    tz = service.tz_label(offset)
    if session_id is not None:
        session = service.get_session_for_report(db, session_id, user)
        return service.report_title(session, offset), service.session_sections(db, session_id, offset), f"session_{session_id}"

    if course_id is not None:
        course = db.get(Course, course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        if user.role == Role.lecturer and not can_teach(course, user):
            raise HTTPException(status_code=403, detail="You do not teach this course")
        sessions = finished_sessions(db, [course_id])
        title = f"Attendance: {course.code} {course.title} ({tz})"
        return title, service.multi_session_sections(db, sessions, offset), f"course_{course_id}"

    if user.role == Role.lecturer:
        lecturer_id = user.id
    if lecturer_id is not None:
        ids = {c.id for c in db.query(Course).filter(Course.lecturer_id == lecturer_id).all()}
        ids |= {s.course_id for s in db.query(ClassSession).filter(ClassSession.lecturer_id == lecturer_id).all()}
        sessions = finished_sessions(db, ids)
        lecturer = db.get(Profile, lecturer_id)
        name = lecturer.full_name if lecturer else f"lecturer {lecturer_id}"
        title = f"Attendance: courses of {name} ({tz})"
        return title, service.multi_session_sections(db, sessions, offset), f"lecturer_{lecturer_id}"

    if department_id is not None:
        department = db.get(Department, department_id)
        if department is None:
            raise HTTPException(status_code=404, detail="Department not found")
        ids = [c.id for c in db.query(Course).filter(Course.department_id == department_id).all()]
        sessions = finished_sessions(db, ids)
        title = f"Attendance: {department.name} ({tz})"
        return title, service.multi_session_sections(db, sessions, offset), f"department_{department_id}"

    sessions = finished_sessions(db)
    return f"Attendance: institution ({tz})", service.multi_session_sections(db, sessions, offset), "institution"


def _download(content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/attendance.xlsx")
def attendance_excel(
    session_id: Optional[int] = None,
    course_id: Optional[int] = None,
    lecturer_id: Optional[int] = None,
    department_id: Optional[int] = None,
    utc_offset_minutes: int = 0,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_role(Role.lecturer, Role.admin)),
):
    title, sections, stem = _export_content(db, user, session_id, course_id, lecturer_id, department_id, utc_offset_minutes)
    return _download(build_attendance_xlsx(title, sections), XLSX_TYPE, f"attendance_{stem}.xlsx")


@router.get("/attendance.csv")
def attendance_csv(
    session_id: Optional[int] = None,
    course_id: Optional[int] = None,
    lecturer_id: Optional[int] = None,
    department_id: Optional[int] = None,
    utc_offset_minutes: int = 0,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_role(Role.lecturer, Role.admin)),
):
    title, sections, stem = _export_content(db, user, session_id, course_id, lecturer_id, department_id, utc_offset_minutes)
    return _download(build_attendance_csv(title, sections), "text/csv", f"attendance_{stem}.csv")


@router.get("/attendance.pdf")
def attendance_pdf(
    session_id: Optional[int] = None,
    course_id: Optional[int] = None,
    lecturer_id: Optional[int] = None,
    department_id: Optional[int] = None,
    utc_offset_minutes: int = 0,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_role(Role.lecturer, Role.admin)),
):
    title, sections, stem = _export_content(db, user, session_id, course_id, lecturer_id, department_id, utc_offset_minutes)
    return _download(build_attendance_pdf(title, sections), "application/pdf", f"attendance_{stem}.pdf")