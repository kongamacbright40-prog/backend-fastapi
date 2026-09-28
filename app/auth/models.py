from sqlalchemy import Column, Integer, String, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum

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
    hashed_password = Column(String, nullable=False)#it should be never be the real password but a hashed code
    role = Column(Enum(Role), nullable=False, default=Role.student)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)

    department = relationship("Department", back_populates="members")   