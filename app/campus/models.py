from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    # class_reminder | new_course | attendance_update | live_question | announcement
    type = Column(String, nullable=False, default="announcement")
    reference_id = Column(String, nullable=True)
    action_label = Column(String, nullable=True)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    profile = relationship("Profile")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    actor_name = Column(String, nullable=True)
    severity = Column(String, nullable=False, default="info")  # info | success | warning | critical
    category = Column(String, nullable=True)  # users | courses | attendance | system
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AcademicTerm(Base):
    __tablename__ = "academic_terms"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    code = Column(String, nullable=False, unique=True)
    academic_year = Column(String, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    status = Column(String, nullable=False, default="planned")  # planned | active | archived
    term_type = Column(String, nullable=False, default="Regular")
    teaching_days = Column(Integer, nullable=True)
    enrollment_open = Column(Boolean, nullable=False, default=False)
    add_drop_deadline = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)


class SystemSettings(Base):
    """Institution-wide policies (a single row, id = 1)."""

    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True)
    late_threshold_minutes = Column(Integer, nullable=False, default=15)
    auto_join_leave_recording = Column(Boolean, nullable=False, default=True)
    participation_weight = Column(Integer, nullable=False, default=20)
    strict_geofencing = Column(Boolean, nullable=False, default=False)
    session_timeout_minutes = Column(Integer, nullable=False, default=60)
    enforce_sso = Column(Boolean, nullable=False, default=False)
    minimum_attendance = Column(Float, nullable=False, default=75.0)
    updated_at = Column(DateTime, nullable=True)
