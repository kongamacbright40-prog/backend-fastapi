"""Attendance analytics shared by the report endpoints and academic terms.

Rates are computed over *finished* classes: for every finished class each
student of the course (current roster) is expected; present and late
("partial") count as attended.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.attendance.models import AttendanceRecord, AttendanceStatus
from app.auth.models import Role
from app.classes.models import ClassSession
from app.courses.models import Course
from app.courses.service import course_students

ATTENDED = (AttendanceStatus.present, AttendanceStatus.partial)


@dataclass
class CourseStats:
    course: Course
    sessions: int = 0
    expected: int = 0
    attended: int = 0
    students: int = 0
    per_student: dict[int, list[int]] = field(default_factory=dict)  # id -> [attended, expected]

    @property
    def rate(self) -> Optional[float]:
        return round(self.attended / self.expected * 100, 1) if self.expected else None


def finished_sessions(
    db: Session,
    course_ids: Optional[Iterable[int]] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> list[ClassSession]:
    query = db.query(ClassSession).filter(ClassSession.ended_at.isnot(None))
    if course_ids is not None:
        ids = list(course_ids)
        query = query.filter(ClassSession.course_id.in_(ids or [-1]))
    if since is not None:
        query = query.filter(ClassSession.started_at >= since)
    if until is not None:
        query = query.filter(ClassSession.started_at <= until)
    return query.all()


def course_stats(db: Session, sessions: list[ClassSession]) -> dict[int, CourseStats]:
    by_course: dict[int, list[ClassSession]] = defaultdict(list)
    for s in sessions:
        by_course[s.course_id].append(s)

    session_ids = [s.id for s in sessions]
    attended_by_session: dict[int, set[int]] = defaultdict(set)
    excused_by_session: dict[int, set[int]] = defaultdict(set)
    if session_ids:
        for r in db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id.in_(session_ids),
            AttendanceRecord.role_at_time == Role.student,
            AttendanceRecord.status.in_(ATTENDED + (AttendanceStatus.excused,)),
        ):
            target = excused_by_session if r.status == AttendanceStatus.excused else attended_by_session
            target[r.session_id].add(r.profile_id)

    result = {}
    for course_id, course_sessions in by_course.items():
        course = course_sessions[0].course
        roster = [p.id for p in course_students(db, course)]
        stats = CourseStats(course=course, sessions=len(course_sessions), students=len(roster))
        for pid in roster:
            stats.per_student[pid] = [0, 0]
        for s in course_sessions:
            present = attended_by_session.get(s.id, set())
            excused = excused_by_session.get(s.id, set())
            for pid in roster:
                if pid in excused:
                    continue  # excused classes are left out of the rate
                stats.per_student[pid][1] += 1
                stats.expected += 1
                if pid in present:
                    stats.per_student[pid][0] += 1
                    stats.attended += 1
        result[course_id] = stats
    return result


def overall_rate(stats: Iterable[CourseStats]) -> Optional[float]:
    expected = attended = 0
    for s in stats:
        expected += s.expected
        attended += s.attended
    return round(attended / expected * 100, 1) if expected else None


def at_risk_students(stats: Iterable[CourseStats], minimum: float) -> set[int]:
    totals: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for s in stats:
        for pid, (att, exp) in s.per_student.items():
            totals[pid][0] += att
            totals[pid][1] += exp
    return {pid for pid, (att, exp) in totals.items() if exp and att / exp * 100 < minimum}


def weekly_trend(db: Session, sessions: list[ClassSession], weeks: int = 8) -> list[dict]:
    """Attendance rate per week (oldest first) for the last ``weeks`` weeks."""
    now = datetime.utcnow()
    start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    points = []
    for i in range(weeks - 1, -1, -1):
        begin = start_of_week - timedelta(weeks=i)
        end = begin + timedelta(weeks=1)
        in_week = [s for s in sessions if s.started_at and begin <= s.started_at < end]
        if not in_week:
            continue
        rate = overall_rate(course_stats(db, in_week).values())
        points.append(
            {
                "label": f"W{weeks - i}",
                "value": rate if rate is not None else 0.0,
                "extra": float(len(in_week)),
            }
        )
    return points
