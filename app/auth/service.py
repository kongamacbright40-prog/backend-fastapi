from sqlalchemy import func
import logging
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.models import PasswordResetCode, Profile
from app.auth.schemas import ProfileCreate
from app.auth.security import hash_password
from app.courses.models import Department

logger = logging.getLogger("smart_class.auth")

RESET_CODE_LENGTH = 4
RESET_CODE_TTL = timedelta(minutes=15)
MAX_RESET_ATTEMPTS = 5


def create_profile(db: Session, payload: ProfileCreate) -> Profile:
    existing = db.query(Profile).filter(func.lower(Profile.email) == payload.email).first()
    if existing is not None:
        if existing.pending_activation:
            return activate_profile(db, existing, payload)
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


def activate_profile(db: Session, user: Profile, payload: ProfileCreate) -> Profile:
    """Completes an account an admin created without a password."""
    if payload.role != user.role:
        raise HTTPException(
            status_code=400,
            detail=f"This email belongs to a {user.role.value} account",
        )
    if payload.matricule_number:
        if user.matricule_number and user.matricule_number != payload.matricule_number:
            raise HTTPException(status_code=400, detail="The ID does not match this account")
        if not user.matricule_number:
            taken = (
                db.query(Profile)
                .filter(Profile.matricule_number == payload.matricule_number, Profile.id != user.id)
                .first()
            )
            if taken:
                raise HTTPException(status_code=400, detail="Matricule number already registered")
            user.matricule_number = payload.matricule_number
    if payload.department_id is not None and user.department_id is None:
        if db.query(Department).filter(Department.id == payload.department_id).first() is None:
            raise HTTPException(status_code=404, detail="Department not found")
        user.department_id = payload.department_id
    if payload.phone_number and not user.phone_number:
        user.phone_number = payload.phone_number
    user.hashed_password = hash_password(payload.password)
    user.pending_activation = False
    db.commit()
    db.refresh(user)
    return user


def unusable_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


def issue_reset_code(db: Session, email: str) -> None:
    """Creates a reset code. Without an e-mail service it is written to the
    server log (look for "Password reset code")."""
    user = db.query(Profile).filter(func.lower(Profile.email) == email).first()
    if user is None or not user.is_active:
        return  # don't reveal which emails exist
    db.query(PasswordResetCode).filter(
        PasswordResetCode.profile_id == user.id, PasswordResetCode.used == False  # noqa: E712
    ).update({"used": True})
    code = "".join(secrets.choice("0123456789") for _ in range(RESET_CODE_LENGTH))
    db.add(
        PasswordResetCode(
            profile_id=user.id,
            code=code,
            expires_at=datetime.utcnow() + RESET_CODE_TTL,
        )
    )
    db.commit()
    logger.warning("Password reset code for %s: %s (valid 15 minutes)", email, code)
    print(f"[smart-class] Password reset code for {email}: {code} (valid 15 minutes)", flush=True)


def find_valid_code(db: Session, email: str, code: str) -> PasswordResetCode:
    """Returns the user's active reset code if ``code`` matches it. Every wrong
    guess counts against the code, and it is invalidated after
    ``MAX_RESET_ATTEMPTS`` so the short code can't be brute-forced."""
    invalid = HTTPException(status_code=400, detail="Invalid or expired code")
    user = db.query(Profile).filter(func.lower(Profile.email) == email).first()
    if user is None:
        raise invalid
    record = (
        db.query(PasswordResetCode)
        .filter(
            PasswordResetCode.profile_id == user.id,
            PasswordResetCode.used == False,  # noqa: E712
        )
        .order_by(PasswordResetCode.id.desc())
        .first()
    )
    if record is None or record.expires_at < datetime.utcnow():
        raise invalid
    if not secrets.compare_digest(record.code, code.strip()):
        record.attempts = (record.attempts or 0) + 1
        if record.attempts >= MAX_RESET_ATTEMPTS:
            record.used = True
        db.commit()
        raise invalid
    return record
