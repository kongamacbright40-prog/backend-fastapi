from typing import Optional

from pydantic import BaseModel


class FacultyCreate(BaseModel):
    name: str


class FacultyOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class FacultyStatsOut(FacultyOut):
    department_count: int = 0
    course_count: int = 0
    student_count: int = 0
    staff_count: int = 0


class DepartmentCreate(BaseModel):
    name: str
    faculty_id: int


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    faculty_id: Optional[int] = None


class DepartmentOut(BaseModel):
    id: int
    name: str
    faculty: FacultyOut
    is_active: bool = True

    class Config:
        from_attributes = True


class DepartmentStatsOut(DepartmentOut):
    course_count: int = 0
    student_count: int = 0
    staff_count: int = 0


class LecturerSummary(BaseModel):
    id: int
    full_name: str

    class Config:
        from_attributes = True


class CourseCreate(BaseModel):
    code: str
    title: str
    department_id: int
    description: Optional[str] = None
    credits: Optional[int] = None
    lecturer_id: Optional[int] = None


class CourseUpdate(BaseModel):
    code: Optional[str] = None
    title: Optional[str] = None
    department_id: Optional[int] = None
    description: Optional[str] = None
    credits: Optional[int] = None


class AssignLecturer(BaseModel):
    lecturer_id: int


class EnrollmentCreate(BaseModel):
    profile_id: int


class CourseOut(BaseModel):
    id: int
    code: str
    title: str
    description: Optional[str] = None
    credits: Optional[int] = None
    is_archived: bool = False
    department: DepartmentOut
    lecturer: Optional[LecturerSummary] = None
    enrolled_count: int = 0
    sessions_held: int = 0
    # Only for students: "department", "explicit" or null (not enrolled).
    enrollment: Optional[str] = None

    class Config:
        from_attributes = True


class StudentOut(BaseModel):
    id: int
    full_name: str
    email: str
    phone_number: Optional[str] = None
    matricule_number: Optional[str] = None
    department: Optional[DepartmentOut] = None

    class Config:
        from_attributes = True
