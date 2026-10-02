from datetime import datetime, timedelta
from typing import Optional

from jose import jwt
from passlib.context import CryptContext

from app.config import settings

# One-way password hashing. Cost 10 takes ~0.1 s per hash/verify on a laptop
# (cost 12, the passlib default, took ~0.5 s and made register + login slow).
# Hashes made with another cost still verify: the cost is stored in the hash.
BCRYPT_ROUNDS = 10
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=BCRYPT_ROUNDS)


def warm_up() -> None:
    """Loads the bcrypt backend now so the first login/registration isn't slow."""
    pwd_context.hash("warm-up")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def needs_rehash(hashed_password: str) -> bool:
    """True for hashes made with a different bcrypt cost than BCRYPT_ROUNDS."""
    try:
        return int(hashed_password.split("$")[2]) != BCRYPT_ROUNDS
    except (IndexError, ValueError):
        return False

def create_access_token(subject: str, extra_claims: dict = None) -> str:
    to_encode = {"sub": subject, "type": "access"}
    if extra_claims:
        to_encode.update(extra_claims)
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes) 
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm) 

def create_refresh_token(subject: str) -> str:
    to_encode = {"sub": subject, "type": "refresh"} 
    expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)