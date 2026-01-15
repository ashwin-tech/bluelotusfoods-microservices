from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # SMTP Configuration - Optional for testing
    smtp_server: str
    smtp_port: int
    smtp_username: Optional[str]
    smtp_password: Optional[str]
    smtp_use_tls: bool
    from_email: Optional[str]
    from_name: str
    
    # Email Configuration
    email_simulation_mode: bool  # Set to True to simulate email sending without actual SMTP
    
    class Config:
        env_file = ".env"
        case_sensitive = False  # Allow case-insensitive environment variable matching
        extra = "ignore"  # Ignore extra environment variables not in the model


settings = Settings()
