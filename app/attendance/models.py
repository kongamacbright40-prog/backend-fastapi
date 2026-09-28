import enum
from sqlalchemy import Column, Integer, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship

from app.database import Base
from app.auth.models import Role


class AttendanceStatus(str, enum.Enum):
    present = "present"
    partial = "partial"
    absent = "absent"


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