
import asyncio
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # Maps user_id (str) to a set of active WebSockets for O(1) ops & duplicate prevention
        self.active_connections: dict[str, set[WebSocket]] = {}

    def _normalize_key(self, user_id: str | None) -> str:
        return str(user_id).lower().strip() if user_id else ""

    def connect(self, user_id: str, websocket: WebSocket):
        key = self._normalize_key(user_id)
        if key not in self.active_connections:
            self.active_connections[key] = set()
        self.active_connections[key].add(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket):
        key = self._normalize_key(user_id)
        if key in self.active_connections:
            self.active_connections[key].discard(websocket)
            if not self.active_connections[key]:
                del self.active_connections[key]

    def is_user_online(self, user_id: str) -> bool:
        key = self._normalize_key(user_id)
        return key in self.active_connections and len(self.active_connections[key]) > 0

    async def _send_safe(self, websocket: WebSocket, user_id: str, message: dict):
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"[WS SEND ERROR] Removing stale socket for user {user_id}: {e}")
            self.disconnect(user_id, websocket)

    async def send_personal_message(self, message: dict, user_id: str):
        key = self._normalize_key(user_id)
        if key in self.active_connections:
            sockets = list(self.active_connections[key])
            if sockets:
                await asyncio.gather(*[self._send_safe(ws, key, message) for ws in sockets], return_exceptions=True)

    async def send_to_users(self, message: dict, user_ids: list[str] | set[str]):
        tasks = []
        for uid in user_ids:
            key = self._normalize_key(uid)
            if key in self.active_connections:
                for ws in list(self.active_connections[key]):
                    tasks.append(self._send_safe(ws, key, message))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast(self, message: dict):
        tasks = []
        for key, sockets in list(self.active_connections.items()):
            for ws in list(sockets):
                tasks.append(self._send_safe(ws, key, message))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


connection_manager = ConnectionManager()
