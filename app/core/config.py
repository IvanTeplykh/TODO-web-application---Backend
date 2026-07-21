from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REMEMBER_ME_EXPIRE_DAYS: int = 30
    DEFAULT_TOKEN_EXPIRE_DAYS: int = 1
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "todo_db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
