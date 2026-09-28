from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        # session_id -> { profile_id: WebSocket }
        self.rooms: dict[int, dict[int, WebSocket]] = {}

    async def connect(self, session_id: int, peer_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        room = self.rooms.setdefault(session_id, {})
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
        if not room:
            del self.rooms[session_id]
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