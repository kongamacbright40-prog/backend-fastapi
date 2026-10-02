from typing import Optional

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.common.emails import Email

from app.auth.models import Role
from app.common.timeutils import UTCDateTime
from app.courses.schemas import DepartmentOut

# Shortest password accepted (the app's AppConstants.minPasswordLength).
MIN_PASSWORD_LENGTH = 4


class ProfileCreate(BaseModel):
    full_name: str
    email: Email
    phone_number: Optional[str] = None
    matricule_number: Optional[str] = None
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    role: Role = Role.student
    department_id: Optional[int] = None
    # Required to register as admin once an admin exists (ADMIN_REGISTRATION_CODE).
    admin_code: Optional[str] = None

    @model_validator(mode="after")
    def matricule_required_for_students_and_lecturers(self):
        if self.role in (Role.student, Role.lecturer) and not self.matricule_number:
            raise ValueError("matricule_number is required for students and lecturers")
        return self


class ProfileOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone_number: Optional[str]
    matricule_number: Optional[str]
    role: Role
    department_id: Optional[int] = None
    department: Optional[DepartmentOut] = None
    is_active: bool = True
    pending_activation: bool = False
    created_at: Optional[UTCDateTime] = None
    last_login_at: Optional[UTCDateTime] = None

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2)
    phone_number: Optional[str] = None


class LoginRequest(BaseModel):
    email: Email
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class PasswordResetRequest(BaseModel):
    email: Email


class PasswordResetVerify(BaseModel):
    email: Email
    code: str


class PasswordResetConfirm(BaseModel):
    email: Email
    code: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)
