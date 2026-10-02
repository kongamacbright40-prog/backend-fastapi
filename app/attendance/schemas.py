from typing import Optional

from pydantic import BaseModel, Field

from app.attendance.models import AppealStatus, AttendanceStatus
from app.classes.schemas import CourseSummary, LecturerSummary
from app.common.timeutils import UTCDateTime


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
    joined_at: Optional[UTCDateTime]
    left_at: Optional[UTCDateTime]
    duration_seconds: int

    class Config:
        from_attributes = True


class SessionBrief(BaseModel):
    id: int
    title: Optional[str] = None
    started_at: Optional[UTCDateTime] = None
    ended_at: Optional[UTCDateTime] = None
    duration_minutes: Optional[int] = None
    course: CourseSummary
    lecturer: Optional[LecturerSummary] = None


class MyAttendanceOut(BaseModel):
    """One held class of the student's courses (absent when never joined)."""

    session: SessionBrief
    record_id: Optional[int] = None
    status: AttendanceStatus
    joined_at: Optional[UTCDateTime] = None
    left_at: Optional[UTCDateTime] = None
    duration_seconds: int = 0


class CourseAttendanceSummary(BaseModel):
    profile: ProfileSummary
    total_sessions: int
    present_count: int
    late_count: int
    absent_count: int
    excused_count: int = 0


class AppealCreate(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    document_name: Optional[str] = None


class AppealOut(BaseModel):
    id: int
    session_id: int
    profile_id: int
    reason: str
    document_name: Optional[str]
    status: AppealStatus
    created_at: UTCDateTime

    class Config:
        from_attributes = True
