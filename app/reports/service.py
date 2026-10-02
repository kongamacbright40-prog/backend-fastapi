from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.models import Role, Profile
from app.classes.models import ClassSession
from app.attendance.models import AttendanceRecord


def get_session_for_report(db: Session, session_id: int, user: Profile) -> ClassSession:
    session = db.query(ClassSession).filter(ClassSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if user.role == Role.lecturer and session.lecturer_id != user.id:
        raise HTTPException(status_code=403, detail="You do not own this session")
    return session


def tz_label(offset: timedelta) -> str:
    """e.g. "UTC+01:00" for the clock the report times are shown in."""
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    return f"UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def _clock(value: Optional[datetime], offset: timedelta) -> str:
    return (value + offset).strftime("%H:%M:%S") if value else ""


def class_label(session: ClassSession, offset: timedelta = timedelta(0)) -> str:
    start = session.started_at or session.scheduled_start
    when = (start + offset).strftime("%Y-%m-%d %H:%M") if start else "not started"
    return f"{when} {session.title or session.course.code}"


def report_title(session: ClassSession, offset: timedelta = timedelta(0)) -> str:
    return f"Attendance: {session.course.code} {session.course.title}, {class_label(session, offset)} ({tz_label(offset)})"


def _record_row(record: AttendanceRecord, offset: timedelta, session: Optional[ClassSession] = None) -> dict:
    return {
        "class": class_label(session, offset) if session is not None else "",
        "matricule": record.profile.matricule_number or "",
        "full_name": record.profile.full_name,
        "role": record.role_at_time.value,
        "status": record.status.value,
        "joined_at": _clock(record.joined_at, offset),
        "left_at": _clock(record.left_at, offset),
        "duration_minutes": round((record.duration_seconds or 0) / 60, 1),
    }


def get_attendance_rows(db: Session, session_id: int, offset: timedelta = timedelta(0)) -> list[dict]:
    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.session_id == session_id)
        .order_by(AttendanceRecord.id)
        .all()
    )
    return [_record_row(record, offset) for record in records]


def get_detail_rows(db: Session, sessions: list[ClassSession], offset: timedelta = timedelta(0)) -> list[dict]:
    """One row per person per class (join / leave times), oldest class first."""
    by_id = {s.id: s for s in sessions}
    if not by_id:
        return []
    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.session_id.in_(list(by_id)))
        .all()
    )

    def order(record: AttendanceRecord):
        session = by_id[record.session_id]
        start = session.started_at or session.scheduled_start or datetime.min
        return (start, session.id, record.role_at_time.value != "lecturer", record.profile.full_name)

    return [_record_row(r, offset, by_id[r.session_id]) for r in sorted(records, key=order)]

def get_aggregate_rows(db: Session, sessions: list[ClassSession]) -> list[dict]:
    """One row per student over several finished classes."""
    from app.reports.analytics import course_stats

    stats = course_stats(db, sessions)
    minutes: dict[int, float] = {}
    session_ids = [s.id for s in sessions]
    if session_ids:
        for record in db.query(AttendanceRecord).filter(AttendanceRecord.session_id.in_(session_ids)):
            minutes[record.profile_id] = minutes.get(record.profile_id, 0) + (record.duration_seconds or 0) / 60

    totals: dict[int, list[int]] = {}
    for course in stats.values():
        for pid, (attended, expected) in course.per_student.items():
            entry = totals.setdefault(pid, [0, 0])
            entry[0] += attended
            entry[1] += expected

    profiles = {p.id: p for p in db.query(Profile).filter(Profile.id.in_(list(totals) or [-1])).all()}
    rows = []
    for pid, (attended, expected) in sorted(totals.items(), key=lambda kv: profiles[kv[0]].full_name):
        rate = attended / expected * 100 if expected else 0
        rows.append(
            {
                "matricule": profiles[pid].matricule_number or "",
                "full_name": profiles[pid].full_name,
                "role": profiles[pid].role.value,
                "status": f"{attended}/{expected} attended ({rate:.1f}%)",
                "duration_minutes": round(minutes.get(pid, 0), 1),
            }
        )
    return rows


# A report section: (title, column headers, rows of cell values).
Section = tuple[str, list[str], list[list]]


def session_sections(db: Session, session_id: int, offset: timedelta) -> list[Section]:
    tz = tz_label(offset)
    rows = get_attendance_rows(db, session_id, offset)
    return [
        (
            "Attendance",
            ["Matricule", "Full name", "Role", "Status", f"Joined ({tz})", f"Left ({tz})", "Duration (min)"],
            [
                [r["matricule"], r["full_name"], r["role"], r["status"], r["joined_at"], r["left_at"], r["duration_minutes"]]
                for r in rows
            ],
        )
    ]


def multi_session_sections(db: Session, sessions: list[ClassSession], offset: timedelta) -> list[Section]:
    """Per-student totals, then every class with each person's join / leave times."""
    tz = tz_label(offset)
    summary = get_aggregate_rows(db, sessions)
    details = get_detail_rows(db, sessions, offset)
    return [
        (
            "Summary",
            ["Matricule", "Full name", "Role", "Attendance", "Total minutes"],
            [[r["matricule"], r["full_name"], r["role"], r["status"], r["duration_minutes"]] for r in summary],
        ),
        (
            "Class details",
            ["Class", "Matricule", "Full name", "Role", "Status", f"Joined ({tz})", f"Left ({tz})", "Duration (min)"],
            [
                [r["class"], r["matricule"], r["full_name"], r["role"], r["status"], r["joined_at"], r["left_at"], r["duration_minutes"]]
                for r in details
            ],
        ),
    ]
