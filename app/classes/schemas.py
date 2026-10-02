from typing import Optional

from pydantic import BaseModel, Field

from app.auth.models import Role
from app.common.timeutils import UTCDateTime


class LecturerSummary(BaseModel):
    id: int
    full_name: str

    class Config:
        from_attributes = True


class CourseSummary(BaseModel):
    id: int
    code: str
    title: str

    class Config:
        from_attributes = True


class ClassSessionCreate(BaseModel):
    """Starts a class immediately."""

    course_id: int
    title: Optional[str] = None
    duration_minutes: Optional[int] = Field(default=None, gt=0)


class ClassSessionSchedule(BaseModel):
    course_id: int
    title: Optional[str] = None
    scheduled_start: UTCDateTime
    duration_minutes: int = Field(default=60, gt=0)


class ClassSessionOut(BaseModel):
    id: int
    course_id: int
    lecturer_id: int
    title: Optional[str] = None
    scheduled_start: Optional[UTCDateTime] = None
    duration_minutes: Optional[int] = None
    started_at: Optional[UTCDateTime] = None
    ended_at: Optional[UTCDateTime] = None
    status: str = "scheduled"  # scheduled | live | completed
    course: Optional[CourseSummary] = None
    lecturer: Optional[LecturerSummary] = None
    participant_count: int = 0
    expected_count: int = 0

    class Config:
        from_attributes = True


class ParticipantOut(BaseModel):
    user_id: int
    name: str
    role: Role
    joined_at: UTCDateTime
    is_hand_raised: bool = False


class HandUpdate(BaseModel):
    raised: bool


class ChatMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    is_question: bool = False


class ChatMessageOut(BaseModel):
    id: int
    session_id: int
    sender_id: int
    sender_name: str
    sender_role: Role
    message: str
    is_question: bool
    created_at: UTCDateTime
