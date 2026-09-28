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


def report_title(session: ClassSession) -> str:
    started = session.started_at.strftime("%Y-%m-%d %H:%M") if session.started_at else "not started"
    return f"Attendance: {session.course.code} {session.course.title} ({started} UTC)"


def get_attendance_rows(db: Session, session_id: int) -> list[dict]:
    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.session_id == session_id)
        .order_by(AttendanceRecord.id)
        .all()
    )
    rows = []
    for record in records:
        rows.append(
            {
                "matricule": record.profile.matricule_number or "",
                "full_name": record.profile.full_name,
                "role": record.role_at_time.value,
                "status": record.status.value,
                "joined_at": record.joined_at.strftime("%H:%M:%S") if record.joined_at else "",
                "left_at": record.left_at.strftime("%H:%M:%S") if record.left_at else "",
                "duration_minutes": round(record.duration_seconds / 60, 1),
            }
        )
    return rows