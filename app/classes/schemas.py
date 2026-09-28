from pydantic import BaseModel
from typing import Optional
from datetime import datetime

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
    course_id: int


class ClassSessionOut(BaseModel):
    id: int
    course_id: int
    lecturer_id: int
    started_at: Optional[datetime]
    ended_at: Optional[datetime]

    class Config:
        from_attributes = True