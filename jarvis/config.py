from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    anthropic_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    hass_url: str = "http://homeassistant.local:8123"
    hass_token: Optional[str] = None
    twilio_sid: Optional[str] = None
    twilio_token: Optional[str] = None
    twilio_from_number: Optional[str] = None
    user_phone_number: Optional[str] = None

    # Security & Privacy Settings
    master_key: Optional[str] = None
    mfa_secret: Optional[str] = None

    # VS Code Settings (can be overridden by extension payload)
    local_model: str = "llama3.1:8b"
    cloud_model: str = "claude-3-5-sonnet-20241022"  # Fast, state-of-the-art advanced model
    cloud_threshold: float = 0.80  # Higher threshold to prioritize the fast local model
    tts_engine: str = "elevenlabs"
    voice_enabled: bool = True
    critic_enabled: bool = False
    supabase_enabled: bool = True
    project_dirs: List[str] = []
    standup_time: str = "10:00"
    exam_date: Optional[str] = None
    dashboard_username: str = "jarvis"
    dashboard_password: str = "admin123"

    # Local Docker DB (optional)
    db_password: Optional[str] = None
    database_url: Optional[str] = None

    class Config:
        import os
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        extra = "ignore"  # Ignore unknown env vars — prevents crashes on new .env additions

settings = Settings()
