from typing import Optional

from pydantic import BaseModel, EmailStr, model_validator

from app.auth.models import Role


class ProfileCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone_number: Optional[str] = None
    matricule_number: Optional[str] = None
    password: str
    role: Role = Role.student
    department_id: Optional[int] = None

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

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str