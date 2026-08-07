from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "super_secret_default_jwt_signing_key_2026_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200
    REMEMBER_ME_EXPIRE_DAYS: int = 30
    DEFAULT_TOKEN_EXPIRE_DAYS: int = 1
    DATABASE_URL: str = "sqlite+aiosqlite:///./todo.db"
    ENCRYPTION_KEY: str = "super_secret_aes256_gcm_32byte_key_001"
    HMAC_KEY: str = "super_secret_hmac_sha256_indexing_key_001"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
