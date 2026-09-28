from typing import Optional

from pydantic import BaseModel, EmailStr

from app.auth.models import Role
from app.courses.schemas import DepartmentOut


class AdminUserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone_number: Optional[str]
    matricule_number: Optional[str]
    role: Role
    department: Optional[DepartmentOut]

    class Config:
        from_attributes = True


class AssignDepartment(BaseModel):
    department_id: int


class TeachingHoursRow(BaseModel):
    lecturer_id: int
    full_name: str
    sessions_count: int
    total_hours: float


class AttendanceHoursRow(BaseModel):
    profile_id: int
    full_name: str
    matricule_number: Optional[str]
    role: Role
    sessions_attended: int
    total_hours: float