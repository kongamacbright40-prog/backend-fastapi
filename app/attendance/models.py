import enum
from datetime import datetime

from sqlalchemy import Column, Integer, ForeignKey, DateTime, Enum, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.auth.models import Role


class AttendanceStatus(str, enum.Enum):
    present = "present"
    partial = "partial"  # late arrival
    absent = "absent"
    excused = "excused"  # does not count against the student


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), nullable=False)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    role_at_time = Column(Enum(Role), nullable=False)
    status = Column(Enum(AttendanceStatus), nullable=False, default=AttendanceStatus.absent)
    joined_at = Column(DateTime, nullable=True)
    left_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, default=0)

    session = relationship("ClassSession", back_populates="attendance_records")
    profile = relationship("Profile")


class AppealStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class AttendanceAppeal(Base):
    __tablename__ = "attendance_appeals"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), nullable=False)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    reason = Column(Text, nullable=False)
    document_name = Column(String, nullable=True)
    status = Column(Enum(AppealStatus), nullable=False, default=AppealStatus.pending)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    session = relationship("ClassSession")
    profile = relationship("Profile")