"""Course membership rules.

A student is enrolled in a course when there is an explicit ``Enrollment`` or
when the course belongs to the student's department (and is not archived).
"""

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.models import Profile, Role
from app.courses.models import Course, Enrollment


def student_courses_query(db: Session, student: Profile):
    explicit = db.query(Enrollment.course_id).filter(Enrollment.profile_id == student.id)
    conditions = [Course.id.in_(explicit)]
    if student.department_id is not None:
        conditions.append(Course.department_id == student.department_id)
    return db.query(Course).filter(Course.is_archived == False, or_(*conditions))  # noqa: E712


def student_course_ids(db: Session, student: Profile) -> set[int]:
    return {c.id for c in student_courses_query(db, student).all()}


def course_students(db: Session, course: Course) -> list[Profile]:
    explicit = db.query(Enrollment.profile_id).filter(Enrollment.course_id == course.id)
    return (
        db.query(Profile)
        .filter(
            Profile.role == Role.student,
            or_(Profile.id.in_(explicit), Profile.department_id == course.department_id),
        )
        .order_by(Profile.full_name)
        .all()
    )


def is_enrolled(db: Session, course: Course, student: Profile) -> bool:
    return student_enrollment(db, course, student) is not None


def student_enrollment(db: Session, course: Course, student: Profile) -> Optional[str]:
    """How [student] takes [course]: "department" (course of their
    department), "explicit" (enrolled individually) or None."""
    if student.department_id is not None and student.department_id == course.department_id:
        return "department"
    explicit = (
        db.query(Enrollment)
        .filter(Enrollment.course_id == course.id, Enrollment.profile_id == student.id)
        .first()
    )
    return "explicit" if explicit is not None else None


def can_teach(course: Course, lecturer: Profile) -> bool:
    """Lecturers teach their assigned courses; unassigned courses are open."""
    return course.lecturer_id is None or course.lecturer_id == lecturer.id
