from typing import Optional

from pydantic import BaseModel, Field

from app.common.timeutils import UTCDateTime


class NotificationOut(BaseModel):
    id: int
    user_id: int
    title: str
    body: str
    type: str
    reference_id: Optional[str] = None
    action_label: Optional[str] = None
    is_read: bool
    created_at: UTCDateTime


class ActivityOut(BaseModel):
    id: int
    title: str
    description: str
    actor_name: Optional[str] = None
    severity: str
    category: Optional[str] = None
    timestamp: UTCDateTime


class AcademicTermIn(BaseModel):
    name: str = Field(min_length=2)
    code: str = Field(min_length=2)
    academic_year: str
    start_date: UTCDateTime
    end_date: UTCDateTime
    status: str = Field(default="planned", pattern="^(planned|active|archived)$")
    term_type: str = "Regular"
    teaching_days: Optional[int] = None
    enrollment_open: bool = False
    add_drop_deadline: Optional[UTCDateTime] = None
    notes: Optional[str] = None


class AcademicTermOut(AcademicTermIn):
    id: int
    enrolled_students: int = 0
    course_count: int = 0
    average_attendance: Optional[float] = None


class SystemSettingsIn(BaseModel):
    late_threshold_minutes: int = Field(ge=0, le=120)
    auto_join_leave_recording: bool
    participation_weight: int = Field(ge=0, le=100)
    strict_geofencing: bool
    session_timeout_minutes: int = Field(ge=5, le=1440)
    enforce_sso: bool
    minimum_attendance: float = Field(ge=0, le=100)


class SystemSettingsOut(SystemSettingsIn):
    cluster_version: str = ""
    last_synced_at: Optional[UTCDateTime] = None
