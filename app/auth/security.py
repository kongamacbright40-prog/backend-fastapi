from datetime import datetime, timedelta
from typing import Optional

from jose import jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")# this is a tool that sturns a password into a scrambled, one way hash

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

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