from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.models import Profile
from app.auth.schemas import ProfileCreate
from app.auth.security import hash_password
from app.courses.models import Department


def create_profile(db: Session, payload: ProfileCreate) -> Profile:
    if db.query(Profile).filter(Profile.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    if payload.matricule_number:
        if db.query(Profile).filter(Profile.matricule_number == payload.matricule_number).first():
            raise HTTPException(status_code=400, detail="Matricule number already registered")

    if payload.department_id is not None:
        if db.query(Department).filter(Department.id == payload.department_id).first() is None:
            raise HTTPException(status_code=404, detail="Department not found")

    user = Profile(
        full_name=payload.full_name,
        email=payload.email,
        phone_number=payload.phone_number,
        matricule_number=payload.matricule_number or None,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        department_id=payload.department_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user