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
    email_simulation_mode: bool = False  # Set to True to simulate email sending without actual SMTP
    
    # Service Configuration
    debug: bool = False
    log_level: str = "INFO"
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8001
    
    class Config:
        env_file = ".env"


settings = Settings()