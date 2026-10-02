from sqlalchemy import func
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.auth.models import Profile, Role
from app.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetVerify,
    ProfileCreate,
    ProfileOut,
    ProfileUpdate,
    RefreshRequest,
    TokenPair,
)
from app.auth.security import create_access_token, create_refresh_token, hash_password, needs_rehash, verify_password
from app.auth.service import create_profile, find_valid_code, issue_reset_code
from app.common.deps import get_current_user
from app.config import settings
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ProfileOut, status_code=201)
def register(payload: ProfileCreate, db: Session = Depends(get_db)):
    if payload.role == Role.admin:
        _check_admin_registration(db, payload)
    return create_profile(db, payload)


def _check_admin_registration(db: Session, payload: ProfileCreate) -> None:
    """The first admin registers freely. After that, registering as admin needs
    ADMIN_REGISTRATION_CODE, except to activate an admin account that an
    existing admin created without a password."""
    if db.query(Profile).filter(Profile.role == Role.admin).first() is None:
        return
    pending = (
        db.query(Profile)
        .filter(func.lower(Profile.email) == payload.email, Profile.role == Role.admin, Profile.pending_activation == True)  # noqa: E712
        .first()
    )
    if pending is not None:
        return
    code = settings.admin_registration_code
    if not code:
        raise HTTPException(
            status_code=403,
            detail="Admin registration is closed. Ask an existing admin to add you.",
        )
    if not secrets.compare_digest((payload.admin_code or "").strip(), code):
        raise HTTPException(status_code=403, detail="Invalid admin registration code")


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(Profile).filter(func.lower(Profile.email) == payload.email).first()
    if user is not None and user.pending_activation:
        raise HTTPException(
            status_code=403,
            detail="Activate your account first (Activate your account / Register as lecturer)",
        )
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account has been deactivated")

    # Re-hash passwords stored with the old, slower bcrypt cost so later
    # logins for this account are fast too.
    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(payload.password)

    user.last_login_at = datetime.utcnow()
    db.commit()
    return TokenPair(
        access_token=create_access_token(str(user.id), {"role": user.role.value}),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.get("/me", response_model=ProfileOut)
def me(user: Profile = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=ProfileOut)
def update_me(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    data = payload.model_dump(exclude_unset=True)
    if data.get("full_name"):
        user.full_name = data["full_name"].strip()
    if "phone_number" in data:
        user.phone_number = (data["phone_number"] or "").strip() or None
    db.commit()
    db.refresh(user)
    return user


@router.post("/change-password", status_code=204)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return Response(status_code=204)


@router.post("/password-reset/request", status_code=204)
def password_reset_request(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    issue_reset_code(db, payload.email)
    return Response(status_code=204)


@router.post("/password-reset/verify", status_code=204)
def password_reset_verify(payload: PasswordResetVerify, db: Session = Depends(get_db)):
    find_valid_code(db, payload.email, payload.code)
    return Response(status_code=204)


@router.post("/password-reset/confirm", status_code=204)
def password_reset_confirm(payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    record = find_valid_code(db, payload.email, payload.code)
    record.used = True
    record.profile.hashed_password = hash_password(payload.new_password)
    record.profile.pending_activation = False
    db.commit()
    return Response(status_code=204)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    invalid = HTTPException(status_code=401, detail="Invalid or expired refresh token")
    try:
        decoded = jwt.decode(payload.refresh_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise invalid
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    try:
        user_id = int(decoded.get("sub"))
    except (TypeError, ValueError):
        raise invalid

    user = db.query(Profile).filter(Profile.id == user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User no longer exists")

    return TokenPair(
        access_token=create_access_token(str(user.id), {"role": user.role.value}),
        refresh_token=create_refresh_token(str(user.id)),
    )
