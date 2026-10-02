from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.common.emails import Email

from app.auth.models import Role
from app.auth.schemas import MIN_PASSWORD_LENGTH
from app.common.timeutils import UTCDateTime
from app.courses.schemas import DepartmentOut


class AdminUserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone_number: Optional[str]
    matricule_number: Optional[str]
    role: Role
    department: Optional[DepartmentOut]
    is_active: bool = True
    pending_activation: bool = False
    created_at: Optional[UTCDateTime] = None
    last_login_at: Optional[UTCDateTime] = None

    class Config:
        from_attributes = True


class AdminUserCreate(BaseModel):
    """Without a password the account is created pending activation: the
    owner sets a password via student activation / lecturer registration."""

    full_name: str = Field(min_length=2)
    email: Email
    role: Role = Role.student
    phone_number: Optional[str] = None
    matricule_number: Optional[str] = None
    department_id: Optional[int] = None
    password: Optional[str] = Field(default=None, min_length=MIN_PASSWORD_LENGTH)


class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2)
    email: Optional[Email] = None
    phone_number: Optional[str] = None
    matricule_number: Optional[str] = None
    department_id: Optional[int] = None


class UserStatusUpdate(BaseModel):
    is_active: bool


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
