from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, UniqueConstraint, false, true
from sqlalchemy.orm import relationship

from app.database import Base


class Faculty(Base):
    __tablename__ = "faculties"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

    departments = relationship("Department", back_populates="faculty")


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    faculty_id = Column(Integer, ForeignKey("faculties.id"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())

    faculty = relationship("Faculty", back_populates="departments")
    members = relationship("Profile", back_populates="department")
    courses = relationship("Course", back_populates="department")


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)
    code = Column(String, nullable=False)
    title = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    lecturer_id = Column(Integer, ForeignKey("profiles.id"), nullable=True)
    description = Column(Text, nullable=True)
    credits = Column(Integer, nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False, server_default=false())

    department = relationship("Department", back_populates="courses")
    lecturer = relationship("Profile", foreign_keys=[lecturer_id])
    enrollments = relationship("Enrollment", back_populates="course")


class Enrollment(Base):
    """Explicit enrolment of a student in a course.

    Students are also implicitly enrolled in every active course of their
    department (see ``app.courses.service``).
    """

    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("course_id", "profile_id", name="one_enrollment_per_student"),)

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)

    course = relationship("Course", back_populates="enrollments")
    profile = relationship("Profile")
