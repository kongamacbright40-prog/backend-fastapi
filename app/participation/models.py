import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Enum,
    ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class QuestionType(str, enum.Enum):
    mcq = "mcq"
    text = "text"


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), nullable=False)
    question_type = Column(Enum(QuestionType), nullable=False, default=QuestionType.mcq)
    prompt = Column(Text, nullable=False)
    correct_answer = Column(String, nullable=True)  # only used for text questions
    is_open = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    session = relationship("ClassSession")
    options = relationship("QuestionOption", back_populates="question")
    responses = relationship("QuestionResponse", back_populates="question")


class QuestionOption(Base):
    __tablename__ = "question_options"

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    text = Column(String, nullable=False)
    is_correct = Column(Boolean, nullable=False, default=False)

    question = relationship("Question", back_populates="options")


class QuestionResponse(Base):
    __tablename__ = "question_responses"
    __table_args__ = (
        UniqueConstraint("question_id", "profile_id", name="one_answer_per_student"),
    )

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    selected_option_id = Column(Integer, ForeignKey("question_options.id"), nullable=True)
    answer_text = Column(String, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    responded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    question = relationship("Question", back_populates="responses")
    profile = relationship("Profile")
    selected_option = relationship("QuestionOption")