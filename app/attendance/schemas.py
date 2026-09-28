from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.attendance.models import AttendanceStatus


class ProfileSummary(BaseModel):
    id: int
    full_name: str
    matricule_number: Optional[str]

    class Config:
        from_attributes = True


class AttendanceMark(BaseModel):
    profile_id: int
    status: AttendanceStatus


class AttendanceOut(BaseModel):
    id: int
    session_id: int
    profile: ProfileSummary
    status: AttendanceStatus
    joined_at: Optional[datetime]
    left_at: Optional[datetime]
    duration_seconds: int

    class Config:
        from_attributes = True