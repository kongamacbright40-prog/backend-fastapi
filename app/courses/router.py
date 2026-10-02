from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.models import Profile, Role
from app.campus.service import log_activity, notify
from app.classes.models import ClassSession
from app.common.deps import get_current_user, require_role
from app.common.pagination import Page, PageParams
from app.courses import models, schemas
from app.courses.service import course_students, student_courses_query, student_enrollment
from app.database import get_db

router = APIRouter(tags=["courses"])


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def course_out(db: Session, course: models.Course, viewer: Optional[Profile] = None) -> schemas.CourseOut:
    held = (
        db.query(func.count(ClassSession.id))
        .filter(ClassSession.course_id == course.id, ClassSession.started_at.isnot(None))
        .scalar()
    )
    enrollment = None
    if viewer is not None and viewer.role == Role.student:
        enrollment = student_enrollment(db, course, viewer)
    return schemas.CourseOut(
        id=course.id,
        code=course.code,
        title=course.title,
        description=course.description,
        credits=course.credits,
        is_archived=bool(course.is_archived),
        department=schemas.DepartmentOut.model_validate(course.department),
        lecturer=schemas.LecturerSummary.model_validate(course.lecturer) if course.lecturer else None,
        enrolled_count=len(course_students(db, course)),
        sessions_held=held or 0,
        enrollment=enrollment,
    )


def department_out(db: Session, department: models.Department) -> schemas.DepartmentStatsOut:
    members = db.query(Profile.role, func.count(Profile.id)).filter(
        Profile.department_id == department.id
    ).group_by(Profile.role).all()
    counts = {role: count for role, count in members}
    return schemas.DepartmentStatsOut(
        id=department.id,
        name=department.name,
        faculty=schemas.FacultyOut.model_validate(department.faculty),
        is_active=bool(department.is_active),
        course_count=db.query(models.Course)
        .filter(models.Course.department_id == department.id, models.Course.is_archived == False)  # noqa: E712
        .count(),
        student_count=counts.get(Role.student, 0),
        staff_count=counts.get(Role.lecturer, 0),
    )


def faculty_out(db: Session, faculty: models.Faculty) -> schemas.FacultyStatsOut:
    department_ids = [d.id for d in faculty.departments]
    members = (
        db.query(Profile.role, func.count(Profile.id))
        .filter(Profile.department_id.in_(department_ids))
        .group_by(Profile.role)
        .all()
        if department_ids
        else []
    )
    counts = {role: count for role, count in members}
    return schemas.FacultyStatsOut(
        id=faculty.id,
        name=faculty.name,
        department_count=len(department_ids),
        course_count=db.query(models.Course).filter(models.Course.department_id.in_(department_ids)).count()
        if department_ids
        else 0,
        student_count=counts.get(Role.student, 0),
        staff_count=counts.get(Role.lecturer, 0),
    )


def get_course_or_404(db: Session, course_id: int) -> models.Course:
    course = db.get(models.Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def get_department_or_404(db: Session, department_id: int) -> models.Department:
    department = db.get(models.Department, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return department


# ---------------------------------------------------------------------------
# Faculties & departments
# ---------------------------------------------------------------------------


@router.post("/faculties", response_model=schemas.FacultyStatsOut)
def create_faculty(
    payload: schemas.FacultyCreate,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    if db.query(models.Faculty).filter(models.Faculty.name == payload.name).first():
        raise HTTPException(status_code=400, detail="A faculty with this name already exists")
    faculty = models.Faculty(name=payload.name)
    db.add(faculty)
    log_activity(db, "Faculty created", payload.name, admin.full_name, "success", "system")
    db.commit()
    db.refresh(faculty)
    return faculty_out(db, faculty)


@router.get("/faculties", response_model=Page[schemas.FacultyStatsOut])
def list_faculties(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _user: Profile = Depends(get_current_user),
):
    query = db.query(models.Faculty).order_by(models.Faculty.id)
    total = query.count()
    items = [faculty_out(db, f) for f in query.offset(params.offset).limit(params.page_size).all()]
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.post("/departments", response_model=schemas.DepartmentStatsOut)
def create_department(
    payload: schemas.DepartmentCreate,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    if db.get(models.Faculty, payload.faculty_id) is None:
        raise HTTPException(status_code=404, detail="Faculty not found")
    if db.query(models.Department).filter(models.Department.name == payload.name).first():
        raise HTTPException(status_code=400, detail="A department with this name already exists")

    department = models.Department(name=payload.name, faculty_id=payload.faculty_id)
    db.add(department)
    log_activity(db, "Department created", payload.name, admin.full_name, "success", "system")
    db.commit()
    db.refresh(department)
    return department_out(db, department)


@router.get("/departments", response_model=Page[schemas.DepartmentStatsOut])
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
    items = [department_out(db, d) for d in query.offset(params.offset).limit(params.page_size).all()]
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.patch("/departments/{department_id}", response_model=schemas.DepartmentStatsOut)
def update_department(
    department_id: int,
    payload: schemas.DepartmentUpdate,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    department = get_department_or_404(db, department_id)
    if payload.faculty_id is not None:
        if db.get(models.Faculty, payload.faculty_id) is None:
            raise HTTPException(status_code=404, detail="Faculty not found")
        department.faculty_id = payload.faculty_id
    if payload.name is not None and payload.name != department.name:
        if db.query(models.Department).filter(models.Department.name == payload.name).first():
            raise HTTPException(status_code=400, detail="A department with this name already exists")
        department.name = payload.name
    log_activity(db, "Department updated", department.name, admin.full_name, "info", "system")
    db.commit()
    db.refresh(department)
    return department_out(db, department)


@router.post("/departments/{department_id}/archive", response_model=schemas.DepartmentStatsOut)
def archive_department(
    department_id: int,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    department = get_department_or_404(db, department_id)
    department.is_active = False
    log_activity(db, "Department archived", department.name, admin.full_name, "warning", "system")
    db.commit()
    db.refresh(department)
    return department_out(db, department)


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


@router.post("/courses", response_model=schemas.CourseOut)
def create_course(
    payload: schemas.CourseCreate,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    get_department_or_404(db, payload.department_id)
    if payload.lecturer_id is not None:
        _get_lecturer(db, payload.lecturer_id)

    course = models.Course(
        code=payload.code,
        title=payload.title,
        department_id=payload.department_id,
        description=payload.description,
        credits=payload.credits,
        lecturer_id=payload.lecturer_id,
    )
    db.add(course)
    log_activity(db, "Course created", f"{payload.code} — {payload.title}", admin.full_name, "success", "courses")
    db.commit()
    db.refresh(course)
    return course_out(db, course)


@router.get("/courses", response_model=Page[schemas.CourseOut])
def list_courses(
    department_id: Optional[int] = None,
    include_archived: bool = False,
    q: Optional[str] = None,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    query = db.query(models.Course)
    if department_id is not None:
        query = query.filter(models.Course.department_id == department_id)
    if not include_archived:
        query = query.filter(models.Course.is_archived == False)  # noqa: E712
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(models.Course.code.ilike(like) | models.Course.title.ilike(like))
    query = query.order_by(models.Course.id)

    total = query.count()
    items = [course_out(db, c, user) for c in query.offset(params.offset).limit(params.page_size).all()]
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.get("/courses/mine", response_model=Page[schemas.CourseOut])
def my_courses(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    """Students: enrolled courses. Lecturers: assigned courses. Admins: all."""
    if user.role == Role.student:
        query = student_courses_query(db, user)
    elif user.role == Role.lecturer:
        query = db.query(models.Course).filter(
            models.Course.lecturer_id == user.id, models.Course.is_archived == False  # noqa: E712
        )
    else:
        query = db.query(models.Course).filter(models.Course.is_archived == False)  # noqa: E712
    query = query.order_by(models.Course.id)
    total = query.count()
    items = [course_out(db, c, user) for c in query.offset(params.offset).limit(params.page_size).all()]
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.get("/courses/{course_id}", response_model=schemas.CourseOut)
def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    return course_out(db, get_course_or_404(db, course_id), user)


@router.patch("/courses/{course_id}", response_model=schemas.CourseOut)
def update_course(
    course_id: int,
    payload: schemas.CourseUpdate,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    course = get_course_or_404(db, course_id)
    data = payload.model_dump(exclude_unset=True)
    if "department_id" in data and data["department_id"] is not None:
        get_department_or_404(db, data["department_id"])
    for field, value in data.items():
        if field in ("code", "title", "department_id") and value is None:
            continue
        setattr(course, field, value)
    log_activity(db, "Course updated", f"{course.code} — {course.title}", admin.full_name, "info", "courses")
    db.commit()
    db.refresh(course)
    return course_out(db, course)


def _get_lecturer(db: Session, lecturer_id: int) -> Profile:
    lecturer = db.get(Profile, lecturer_id)
    if lecturer is None or lecturer.role != Role.lecturer:
        raise HTTPException(status_code=404, detail="Lecturer not found")
    return lecturer


@router.post("/courses/{course_id}/assign-lecturer", response_model=schemas.CourseOut)
def assign_lecturer(
    course_id: int,
    payload: schemas.AssignLecturer,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    course = get_course_or_404(db, course_id)
    lecturer = _get_lecturer(db, payload.lecturer_id)
    course.lecturer_id = lecturer.id
    notify(
        db,
        [lecturer.id],
        "New course assigned",
        f"You now teach {course.code} — {course.title}.",
        type="new_course",
        reference_id=str(course.id),
    )
    log_activity(
        db,
        "Lecturer assigned",
        f"{lecturer.full_name} → {course.code}",
        admin.full_name,
        "success",
        "courses",
    )
    db.commit()
    db.refresh(course)
    return course_out(db, course)


@router.post("/courses/{course_id}/archive", response_model=schemas.CourseOut)
def archive_course(
    course_id: int,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    course = get_course_or_404(db, course_id)
    course.is_archived = True
    log_activity(db, "Course archived", f"{course.code} — {course.title}", admin.full_name, "warning", "courses")
    db.commit()
    db.refresh(course)
    return course_out(db, course)


@router.get("/courses/{course_id}/roster", response_model=list[schemas.StudentOut])
def course_roster(
    course_id: int,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_role(Role.lecturer, Role.admin)),
):
    course = get_course_or_404(db, course_id)
    if user.role == Role.lecturer and course.lecturer_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="You do not teach this course")
    return course_students(db, course)


@router.post("/courses/{course_id}/enrollments", response_model=schemas.CourseOut, status_code=201)
def enroll_student(
    course_id: int,
    payload: schemas.EnrollmentCreate,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    course = get_course_or_404(db, course_id)
    student = db.get(Profile, payload.profile_id)
    if student is None or student.role != Role.student:
        raise HTTPException(status_code=404, detail="Student not found")
    exists = (
        db.query(models.Enrollment)
        .filter(models.Enrollment.course_id == course.id, models.Enrollment.profile_id == student.id)
        .first()
    )
    if exists is None:
        db.add(models.Enrollment(course_id=course.id, profile_id=student.id))
        notify(
            db,
            [student.id],
            "Enrolled in a new course",
            f"You were enrolled in {course.code} — {course.title}.",
            type="new_course",
            reference_id=str(course.id),
        )
        log_activity(
            db, "Student enrolled", f"{student.full_name} → {course.code}", admin.full_name, "success", "courses"
        )
        db.commit()
    db.refresh(course)
    return course_out(db, course)


@router.delete("/courses/{course_id}/enrollments/{profile_id}", status_code=204)
def unenroll_student(
    course_id: int,
    profile_id: int,
    db: Session = Depends(get_db),
    admin: Profile = Depends(require_role(Role.admin)),
):
    get_course_or_404(db, course_id)
    deleted = (
        db.query(models.Enrollment)
        .filter(models.Enrollment.course_id == course_id, models.Enrollment.profile_id == profile_id)
        .delete()
    )
    if deleted:
        log_activity(db, "Student unenrolled", f"profile {profile_id} from course {course_id}", admin.full_name, "info", "courses")
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Student self-enrollment & public department list
# ---------------------------------------------------------------------------


@router.post("/courses/{course_id}/enroll", response_model=schemas.CourseOut)
def enroll_self(
    course_id: int,
    db: Session = Depends(get_db),
    student: Profile = Depends(require_role(Role.student)),
):
    """A student joins a course (in addition to their department's courses)."""
    course = get_course_or_404(db, course_id)
    if course.is_archived:
        raise HTTPException(status_code=400, detail="This course is archived")
    if student_enrollment(db, course, student) is None:
        db.add(models.Enrollment(course_id=course.id, profile_id=student.id))
        log_activity(db, "Student enrolled", f"{student.full_name} → {course.code}", student.full_name, "success", "courses")
        db.commit()
    db.refresh(course)
    return course_out(db, course, student)


@router.delete("/courses/{course_id}/enroll", response_model=schemas.CourseOut)
def drop_self(
    course_id: int,
    db: Session = Depends(get_db),
    student: Profile = Depends(require_role(Role.student)),
):
    """A student leaves a course they enrolled in individually. Courses of
    their own department can't be dropped."""
    course = get_course_or_404(db, course_id)
    if student_enrollment(db, course, student) == "department":
        raise HTTPException(status_code=400, detail="Courses of your department can't be dropped")
    deleted = (
        db.query(models.Enrollment)
        .filter(models.Enrollment.course_id == course.id, models.Enrollment.profile_id == student.id)
        .delete()
    )
    if deleted:
        log_activity(db, "Student dropped course", f"{student.full_name} ← {course.code}", student.full_name, "info", "courses")
    db.commit()
    db.refresh(course)
    return course_out(db, course, student)


@router.get("/departments/public", response_model=list[schemas.DepartmentOut])
def public_departments(db: Session = Depends(get_db)):
    """Active departments, without login: used by the registration screens."""
    return (
        db.query(models.Department)
        .filter(models.Department.is_active == True)  # noqa: E712
        .order_by(models.Department.name)
        .all()
    )
