import motor.motor_asyncio
from app.core.config import settings

class Database:
    def __init__(self):
        self.client: motor.motor_asyncio.AsyncIOMotorClient = None
        self._db = None

    def connect_to_database(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGODB_URL)
        self._db = self.client[settings.DATABASE_NAME]

    def close_database_connection(self):
        if self.client:
            self.client.close()

    @property
    def database(self):
        return self._db

    @property
    def users_collection(self):
        return self._db["users"]

    @property
    def tasks_collection(self):
        return self._db["tasks"]

    @property
    def messages_collection(self):
        return self._db["messages"]

    @property
    def chat_requests_collection(self):
        return self._db["chat_requests"]

db = Database()
