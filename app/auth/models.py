import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, false, text, true
from sqlalchemy.orm import relationship

from app.database import Base


class Role(str, enum.Enum):
    student = "student"
    lecturer = "lecturer"
    admin = "admin"


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone_number = Column(String, nullable=True)
    matricule_number = Column(String, unique=True, nullable=True)
    hashed_password = Column(String, nullable=False)  # never the real password, only its hash
    role = Column(Enum(Role), nullable=False, default=Role.student)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    # Accounts created by an admin without a password; the owner sets one
    # through student activation / lecturer registration.
    pending_activation = Column(Boolean, nullable=False, default=False, server_default=false())
    created_at = Column(DateTime, nullable=True, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    department = relationship("Department", back_populates="members")


class PasswordResetCode(Base):
    __tablename__ = "password_reset_codes"

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, nullable=False, default=False)
    # Wrong guesses against this code; it is burned after MAX_RESET_ATTEMPTS.
    attempts = Column(Integer, nullable=False, default=0, server_default=text("0"))

    profile = relationship("Profile")
