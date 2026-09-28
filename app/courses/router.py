from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.common.deps import require_role, get_current_user
from app.common.pagination import PageParams, Page
from app.auth.models import Role, Profile
from app.courses import models, schemas

router = APIRouter(tags=["courses"])


@router.post("/faculties", response_model=schemas.FacultyOut)
def create_faculty(
    payload: schemas.FacultyCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_role(Role.admin)),
):
    faculty = models.Faculty(name=payload.name)
    db.add(faculty)
    db.commit()
    db.refresh(faculty)
    return faculty


@router.get("/faculties", response_model=Page[schemas.FacultyOut])
def list_faculties(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _user: Profile = Depends(get_current_user),
):
    query = db.query(models.Faculty).order_by(models.Faculty.id)
    total = query.count()
    items = query.offset(params.offset).limit(params.page_size).all()
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.post("/departments", response_model=schemas.DepartmentOut)
def create_department(
    payload: schemas.DepartmentCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_role(Role.admin)),
):
    faculty = db.query(models.Faculty).filter(models.Faculty.id == payload.faculty_id).first()
    if faculty is None:
        raise HTTPException(status_code=404, detail="Faculty not found")

    department = models.Department(name=payload.name, faculty_id=payload.faculty_id)
    db.add(department)
    db.commit()
    db.refresh(department)
    return department


@router.get("/departments", response_model=Page[schemas.DepartmentOut])
def list_departments(
    faculty_id: Optional[int] = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _user: Profile = Depends(get_current_user),
):
    query = db.query(models.Department)
    if faculty_id is not None:
        query = query.filter(models.Department.faculty_id == faculty_id)
    query = query.order_by(models.Department.id)

    total = query.count()
    items = query.offset(params.offset).limit(params.page_size).all()
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.post("/courses", response_model=schemas.CourseOut)
def create_course(
    payload: schemas.CourseCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_role(Role.admin)),
):
    department = db.query(models.Department).filter(models.Department.id == payload.department_id).first()
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")

    course = models.Course(code=payload.code, title=payload.title, department_id=payload.department_id)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("/courses", response_model=Page[schemas.CourseOut])
def list_courses(
    department_id: Optional[int] = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _user: Profile = Depends(get_current_user),
):
    query = db.query(models.Course)
    if department_id is not None:
        query = query.filter(models.Course.department_id == department_id)
    query = query.order_by(models.Course.id)

    total = query.count()
    items = query.offset(params.offset).limit(params.page_size).all()
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)
