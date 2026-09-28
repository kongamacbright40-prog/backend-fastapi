from pydantic import BaseModel


class FacultyCreate(BaseModel):
    name: str


class FacultyOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class DepartmentCreate(BaseModel):
    name: str
    faculty_id: int


class DepartmentOut(BaseModel):
    id: int
    name: str
    faculty: FacultyOut

    class Config:
        from_attributes = True


class CourseCreate(BaseModel):
    code: str
    title: str
    department_id: int


class CourseOut(BaseModel):
    id: int
    code: str
    title: str
    department: DepartmentOut

    class Config:
        from_attributes = True