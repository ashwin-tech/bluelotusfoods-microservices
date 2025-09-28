from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # Database Configuration
    db_name: str = "postgres"
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    
    # CORS Configuration
    cors_allow_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.1.68:5173",  # Network IP for mobile access
        "http://localhost:5174",     # Alternative port
        "http://192.168.1.68:5174",  # Alternative port on network
        "https://yourdomain.com"
    ]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False
    
    # External Services
    email_service_url: str = "http://localhost:8001"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
