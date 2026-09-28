from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, model_validator

from app.participation.models import QuestionType


class OptionCreate(BaseModel):
    text: str
    is_correct: bool = False


class QuestionCreate(BaseModel):
    question_type: QuestionType = QuestionType.mcq
    prompt: str
    correct_answer: Optional[str] = None
    options: List[OptionCreate] = []

    @model_validator(mode="after")
    def check_question_shape(self):
        if self.question_type == QuestionType.mcq:
            if len(self.options) < 2:
                raise ValueError("An MCQ needs at least 2 options")
            correct_count = sum(1 for option in self.options if option.is_correct)
            if correct_count != 1:
                raise ValueError("An MCQ needs exactly one correct option")
        else:
            if self.options:
                raise ValueError("Text questions cannot have options")
        return self


class OptionOutLecturer(BaseModel):
    id: int
    text: str
    is_correct: bool

    class Config:
        from_attributes = True


class OptionOutStudent(BaseModel):
    id: int
    text: str

    class Config:
        from_attributes = True


class QuestionOutLecturer(BaseModel):
    id: int
    session_id: int
    question_type: QuestionType
    prompt: str
    correct_answer: Optional[str]
    is_open: bool
    created_at: datetime
    options: List[OptionOutLecturer]

    class Config:
        from_attributes = True


class QuestionOutStudent(BaseModel):
    id: int
    session_id: int
    question_type: QuestionType
    prompt: str
    is_open: bool
    created_at: datetime
    options: List[OptionOutStudent]

    class Config:
        from_attributes = True


class ResponseCreate(BaseModel):
    selected_option_id: Optional[int] = None
    answer_text: Optional[str] = None

    @model_validator(mode="after")
    def exactly_one_answer(self):
        if (self.selected_option_id is None) == (self.answer_text is None):
            raise ValueError("Provide either selected_option_id or answer_text, not both and not neither")
        return self


class ResponseOut(BaseModel):
    id: int
    question_id: int
    selected_option_id: Optional[int]
    answer_text: Optional[str]
    is_correct: Optional[bool]
    responded_at: datetime

    class Config:
        from_attributes = True