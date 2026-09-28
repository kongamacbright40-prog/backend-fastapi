from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from app.database import get_db
from app.config import settings
from app.auth.models import Profile, Role
from app.auth.schemas import ProfileCreate, ProfileOut, LoginRequest, TokenPair, RefreshRequest
from app.auth.security import verify_password, create_access_token, create_refresh_token
from app.auth.service import create_profile

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ProfileOut, status_code=201)
def register(payload: ProfileCreate, db: Session = Depends(get_db)):
    if payload.role == Role.admin:
        admin_exists = db.query(Profile).filter(Profile.role == Role.admin).first()
        if admin_exists is not None:
            raise HTTPException(
                status_code=403,
                detail="Admin accounts can only be created by an existing admin",
            )
    return create_profile(db, payload)


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(Profile).filter(Profile.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return TokenPair(
        access_token=create_access_token(str(user.id), {"role": user.role.value}),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        decoded = jwt.decode(payload.refresh_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if decoded.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Not a refresh token")
        user_id = decoded["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = db.query(Profile).filter(Profile.id == int(user_id)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")

    return TokenPair(
        access_token=create_access_token(str(user.id), {"role": user.role.value}),
        refresh_token=create_refresh_token(str(user.id)),
    )