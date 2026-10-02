from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.common.deps import require_role, get_current_user
from app.common.pagination import PageParams, Page
from app.auth.models import Role, Profile
from app.classes.models import ClassSession
from app.attendance.models import AttendanceRecord, AttendanceStatus
from app.participation import models, schemas
from app.campus.service import notify
from app.classes.service import ensure_can_view
from app.courses.service import course_students

router = APIRouter(prefix="/participation", tags=["participation"])


def get_owned_session(session_id: int, lecturer: Profile, db: Session) -> ClassSession:
    session = db.query(ClassSession).filter(ClassSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.lecturer_id != lecturer.id:
        raise HTTPException(status_code=403, detail="You do not own this session")
    return session


@router.post("/sessions/{session_id}/questions", response_model=schemas.QuestionOutLecturer)
def create_question(
    session_id: int,
    payload: schemas.QuestionCreate,
    db: Session = Depends(get_db),
    lecturer: Profile = Depends(require_role(Role.lecturer)),
):
    session = get_owned_session(session_id, lecturer, db)
    if session.ended_at is not None:
        raise HTTPException(status_code=400, detail="Session has ended")

    if payload.launch:
        _close_open_questions(db, session_id)
    question = models.Question(
        session_id=session_id,
        question_type=payload.question_type,
        prompt=payload.prompt,
        correct_answer=payload.correct_answer,
        is_open=payload.launch,
        options=[
            models.QuestionOption(text=option.text, is_correct=option.is_correct)
            for option in payload.options
        ],
    )
    db.add(question)
    if payload.launch:
        _announce_question(db, session, payload.prompt)
    db.commit()
    db.refresh(question)
    return question


def _close_open_questions(db: Session, session_id: int) -> None:
    """Only one question is live at a time."""
    db.query(models.Question).filter(
        models.Question.session_id == session_id, models.Question.is_open == True  # noqa: E712
    ).update({"is_open": False})


def _announce_question(db: Session, session: ClassSession, prompt: str) -> None:
    if session.started_at is None:
        return
    notify(
        db,
        [s.id for s in course_students(db, session.course)],
        f"Live question in {session.course.code}",
        prompt[:140],
        type="live_question",
        reference_id=str(session.id),
        action_label="Answer",
    )


@router.post("/questions/{question_id}/launch", response_model=schemas.QuestionOutLecturer)
def launch_question(
    question_id: int,
    db: Session = Depends(get_db),
    lecturer: Profile = Depends(require_role(Role.lecturer)),
):
    question = db.query(models.Question).filter(models.Question.id == question_id).first()
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    session = get_owned_session(question.session_id, lecturer, db)
    if session.ended_at is not None:
        raise HTTPException(status_code=400, detail="Session has ended")
    if not question.is_open:
        _close_open_questions(db, session.id)
        question.is_open = True
        _announce_question(db, session, question.prompt)
        db.commit()
        db.refresh(question)
    return question


@router.get("/sessions/{session_id}/questions", response_model=Page[schemas.QuestionOutLecturer])
def list_questions_for_lecturer(
    session_id: int,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    lecturer: Profile = Depends(require_role(Role.lecturer)),
):
    get_owned_session(session_id, lecturer, db)

    query = (
        db.query(models.Question)
        .filter(models.Question.session_id == session_id)
        .order_by(models.Question.id)
    )
    total = query.count()
    items = query.offset(params.offset).limit(params.page_size).all()
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.get("/sessions/{session_id}/questions/open", response_model=Page[schemas.QuestionOutStudent])
def list_open_questions(
    session_id: int,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _user: Profile = Depends(get_current_user),
):
    session = db.query(ClassSession).filter(ClassSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    ensure_can_view(db, session, _user)

    query = (
        db.query(models.Question)
        .filter(models.Question.session_id == session_id, models.Question.is_open == True)
        .order_by(models.Question.id)
    )
    total = query.count()
    items = query.offset(params.offset).limit(params.page_size).all()
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.post("/questions/{question_id}/respond", response_model=schemas.ResponseOut)
def respond_to_question(
    question_id: int,
    payload: schemas.ResponseCreate,
    db: Session = Depends(get_db),
    student: Profile = Depends(require_role(Role.student)),
):
    question = db.query(models.Question).filter(models.Question.id == question_id).first()
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    if not question.is_open:
        raise HTTPException(status_code=400, detail="This question is closed")

    in_session = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.session_id == question.session_id,
            AttendanceRecord.profile_id == student.id,
            AttendanceRecord.status != AttendanceStatus.absent,
        )
        .first()
    )
    if in_session is None:
        raise HTTPException(status_code=403, detail="You are not marked present in this session")

    already_answered = (
        db.query(models.QuestionResponse)
        .filter(
            models.QuestionResponse.question_id == question_id,
            models.QuestionResponse.profile_id == student.id,
        )
        .first()
    )
    if already_answered:
        raise HTTPException(status_code=409, detail="You have already answered this question")

    selected_option_id = None
    answer_text = None
    is_correct = None

    if question.question_type == models.QuestionType.mcq:
        if payload.selected_option_id is None:
            raise HTTPException(status_code=400, detail="This is an MCQ: send selected_option_id")
        option = (
            db.query(models.QuestionOption)
            .filter(
                models.QuestionOption.id == payload.selected_option_id,
                models.QuestionOption.question_id == question_id,
            )
            .first()
        )
        if option is None:
            raise HTTPException(status_code=400, detail="That option does not belong to this question")
        selected_option_id = option.id
        is_correct = option.is_correct
    else:
        if payload.answer_text is None:
            raise HTTPException(status_code=400, detail="This is a text question: send answer_text")
        answer_text = payload.answer_text
        if question.correct_answer is not None:
            is_correct = answer_text.strip().lower() == question.correct_answer.strip().lower()

    response = models.QuestionResponse(
        question_id=question_id,
        profile_id=student.id,
        selected_option_id=selected_option_id,
        answer_text=answer_text,
        is_correct=is_correct,
    )
    db.add(response)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="You have already answered this question")
    db.refresh(response)
    return response


@router.post("/questions/{question_id}/close", response_model=schemas.QuestionOutLecturer)
def close_question(
    question_id: int,
    db: Session = Depends(get_db),
    lecturer: Profile = Depends(require_role(Role.lecturer)),
):
    question = db.query(models.Question).filter(models.Question.id == question_id).first()
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    get_owned_session(question.session_id, lecturer, db)

    question.is_open = False
    db.commit()
    db.refresh(question)
    return question

@router.get("/questions/{question_id}/responses/me", response_model=Optional[schemas.ResponseOut])
def my_response(
    question_id: int,
    db: Session = Depends(get_db),
    student: Profile = Depends(require_role(Role.student)),
):
    """The caller's answer to a question, or null when not answered yet."""
    return (
        db.query(models.QuestionResponse)
        .filter(
            models.QuestionResponse.question_id == question_id,
            models.QuestionResponse.profile_id == student.id,
        )
        .first()
    )
