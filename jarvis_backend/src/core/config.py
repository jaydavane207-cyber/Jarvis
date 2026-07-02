from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "JARVIS Production Architecture"
    VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://jarvis:secretpassword@localhost:5432/jarvis_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Security
    SECRET_KEY: str = "super-secret-quantum-key-placeholder"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    
    # Advanced Security Features
    ENABLE_QUANTUM_CRYPTO: bool = True
    QUANTUM_KEY_ROTATION_MINUTES: int = 5
    ENABLE_JAILBREAK_PROTECTION: bool = True
    ENABLE_DIGITAL_TWIN: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=True)

settings = Settings()
