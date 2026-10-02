from datetime import datetime, timedelta

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError

from app.config import settings
from app.database import SessionLocal
from app.auth.models import Profile, Role
from app.campus.service import get_settings
from app.classes.models import ClassSession
from app.courses.service import is_enrolled
from app.attendance.models import AttendanceRecord, AttendanceStatus
from app.signaling.connection_manager import manager

router = APIRouter(tags=["signaling"])

RELAYED_TYPES = {"offer", "answer", "ice_candidate"}


def authorize_join(token: str, class_id: int):
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("type") != "access":
        return None
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None

    db = SessionLocal()
    try:
        user = db.query(Profile).filter(Profile.id == user_id).first()
        session = db.query(ClassSession).filter(ClassSession.id == class_id).first()
        if user is None or not user.is_active or session is None or session.ended_at is not None:
            return None
        if user.role == Role.admin:
            return None
        if user.role == Role.lecturer and session.lecturer_id != user.id:
            return None
        if user.role == Role.student and (
            session.started_at is None or not is_enrolled(db, session.course, user)
        ):
            return None
        return user.id, user.role, user.full_name
    finally:
        db.close()


def auto_recording_enabled() -> bool:
    """Admin setting "Automatic Join / Leave Recording". When off, joining a
    class doesn't touch attendance; the lecturer marks it by hand."""
    db = SessionLocal()
    try:
        return bool(get_settings(db).auto_join_leave_recording)
    finally:
        db.close()


def record_join(class_id: int, profile_id: int, role: Role) -> datetime:
    now = datetime.utcnow()
    db = SessionLocal()
    try:
        record = (
            db.query(AttendanceRecord)
            .filter(AttendanceRecord.session_id == class_id, AttendanceRecord.profile_id == profile_id)
            .first()
        )
        if record is None:
            record = AttendanceRecord(session_id=class_id, profile_id=profile_id, role_at_time=role)
            db.add(record)
        if record.joined_at is None:
            record.joined_at = now
        if record.status in (None, AttendanceStatus.absent):
            session = db.get(ClassSession, class_id)
            threshold = timedelta(minutes=get_settings(db).late_threshold_minutes)
            late = (
                role == Role.student
                and session is not None
                and session.started_at is not None
                and now - session.started_at > threshold
            )
            # "partial" is how the backend records a late arrival.
            record.status = AttendanceStatus.partial if late else AttendanceStatus.present
        record.left_at = None
        db.commit()
    finally:
        db.close()
    return now


def record_leave(class_id: int, profile_id: int, connected_at: datetime, mark_left: bool) -> None:
    now = datetime.utcnow()
    db = SessionLocal()
    try:
        record = (
            db.query(AttendanceRecord)
            .filter(AttendanceRecord.session_id == class_id, AttendanceRecord.profile_id == profile_id)
            .first()
        )
        if record is None:
            return
        record.duration_seconds = (record.duration_seconds or 0) + int((now - connected_at).total_seconds())
        if mark_left:
            record.left_at = now
        db.commit()
    finally:
        db.close()


@router.websocket("/ws/signal/{class_id}")
async def signal(websocket: WebSocket, class_id: int, token: str = Query(...)):
    identity = authorize_join(token, class_id)
    if identity is None:
        await websocket.close(code=1008)
        return
    peer_id, role, full_name = identity

    await manager.connect(class_id, peer_id, websocket)
    auto_record = auto_recording_enabled()
    connected_at = record_join(class_id, peer_id, role) if auto_record else datetime.utcnow()

    existing = [p for p in manager.peers(class_id) if p != peer_id]
    await manager.send_to(class_id, peer_id, {"type": "room_state", "peers": existing})
    board = manager.boards.get(class_id)
    if board is not None and (board.active or board.strokes or board.screen_on):
        await manager.send_to(class_id, peer_id, board.state())
    await manager.broadcast(
        class_id,
        {"type": "peer_joined", "peer_id": peer_id, "full_name": full_name, "role": role.value},
        exclude=peer_id,
    )

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except ValueError:
                await manager.send_to(class_id, peer_id, {"type": "error", "detail": "Invalid JSON"})
                continue
            if not isinstance(data, dict):
                continue

            # Whiteboard: only the lecturer draws; everyone else receives.
            if data.get("type") == "board":
                if role != Role.lecturer:
                    continue
                message = manager.board(class_id).apply(data)
                if message is not None:
                    await manager.broadcast(class_id, message, exclude=peer_id)
                continue

            if data.get("type") not in RELAYED_TYPES:
                continue

            target = data.get("target_peer_id")
            if not isinstance(target, int):
                await manager.send_to(class_id, peer_id, {"type": "error", "detail": "target_peer_id must be a number"})
                continue

            delivered = await manager.send_to(class_id, target, {**data, "from_peer_id": peer_id})
            if not delivered:
                await manager.send_to(class_id, peer_id, {"type": "error", "detail": f"peer {target} is not in this class"})
    except WebSocketDisconnect:
        pass
    finally:
        was_current = manager.disconnect(class_id, peer_id, websocket)
        if auto_record:
            record_leave(class_id, peer_id, connected_at, mark_left=was_current)
        if was_current:
            await manager.broadcast(class_id, {"type": "peer_left", "peer_id": peer_id})