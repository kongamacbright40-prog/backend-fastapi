from datetime import datetime

from fastapi import WebSocket

from app.signaling.whiteboard import Whiteboard


class ConnectionManager:
    def __init__(self) -> None:
        # session_id -> { profile_id: WebSocket }
        self.rooms: dict[int, dict[int, WebSocket]] = {}
        # session_id -> profile ids with a raised hand
        self.hands: dict[int, set[int]] = {}
        # session_id -> lecturer's whiteboard (kept while the class runs)
        self.boards: dict[int, Whiteboard] = {}
        # session_id -> when the last person left (room empty since then)
        self.emptied_at: dict[int, datetime] = {}

    def board(self, session_id: int) -> Whiteboard:
        return self.boards.setdefault(session_id, Whiteboard())

    def set_hand(self, session_id: int, peer_id: int, raised: bool) -> None:
        hands = self.hands.setdefault(session_id, set())
        if raised:
            hands.add(peer_id)
        else:
            hands.discard(peer_id)

    def hand_raised(self, session_id: int, peer_id: int) -> bool:
        return peer_id in self.hands.get(session_id, set())

    async def connect(self, session_id: int, peer_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        room = self.rooms.setdefault(session_id, {})
        self.emptied_at.pop(session_id, None)
        old = room.get(peer_id)
        room[peer_id] = websocket
        if old is not None:
            try:
                await old.close(code=1000)
            except Exception:
                pass

    def disconnect(self, session_id: int, peer_id: int, websocket: WebSocket) -> bool:
        room = self.rooms.get(session_id)
        if room is None or room.get(peer_id) is not websocket:
            return False
        del room[peer_id]
        self.set_hand(session_id, peer_id, False)
        if not room:
            del self.rooms[session_id]
            self.hands.pop(session_id, None)
            self.emptied_at[session_id] = datetime.utcnow()
        return True

    def peers(self, session_id: int) -> list[int]:
        return list(self.rooms.get(session_id, {}).keys())

    async def send_to(self, session_id: int, peer_id: int, message: dict) -> bool:
        websocket = self.rooms.get(session_id, {}).get(peer_id)
        if websocket is None:
            return False
        try:
            await websocket.send_json(message)
        except Exception:
            return False
        return True

    async def broadcast(self, session_id: int, message: dict, exclude: int | None = None) -> None:
        for peer_id in list(self.rooms.get(session_id, {})):
            if peer_id != exclude:
                await self.send_to(session_id, peer_id, message)

    async def close_room(self, session_id: int, message: dict | None = None) -> None:
        self.boards.pop(session_id, None)
        self.emptied_at.pop(session_id, None)
        for peer_id, websocket in list(self.rooms.get(session_id, {}).items()):
            if message is not None:
                try:
                    await websocket.send_json(message)
                except Exception:
                    pass
            try:
                await websocket.close(code=1000)
            except Exception:
                pass


manager = ConnectionManager()