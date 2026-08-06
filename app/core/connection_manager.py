from typing import Dict, List
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        # Maps user_id (str) to a set of active WebSockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    def _normalize_key(self, user_id: str | None) -> str:
        return str(user_id).lower().strip() if user_id else ""

    def connect(self, user_id: str, websocket: WebSocket):
        key = self._normalize_key(user_id)
        if key not in self.active_connections:
            self.active_connections[key] = []
        if websocket not in self.active_connections[key]:
            self.active_connections[key].append(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket):
        key = self._normalize_key(user_id)
        if key in self.active_connections:
            if websocket in self.active_connections[key]:
                self.active_connections[key].remove(websocket)
            if not self.active_connections[key]:
                del self.active_connections[key]

    def is_user_online(self, user_id: str) -> bool:
        key = self._normalize_key(user_id)
        return key in self.active_connections and len(self.active_connections[key]) > 0

    async def send_personal_message(self, message: dict, user_id: str):
        key = self._normalize_key(user_id)
        if key in self.active_connections:
            for connection in list(self.active_connections[key]):
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

    async def broadcast(self, message: dict):
        for user_id, connections in list(self.active_connections.items()):
            for connection in list(connections):
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

connection_manager = ConnectionManager()
