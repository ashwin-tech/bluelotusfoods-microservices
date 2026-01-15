from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Optional, Union
import json


class Settings(BaseSettings):
    # Database Configuration
    db_name: str
    db_user: str
    db_password: str
    db_host: str
    db_port: int
    
    # CORS Configuration - comma-separated origins
    cors_origins: str
    cors_allow_credentials: bool
    cors_allow_methods: Union[str, List[str]]
    cors_allow_headers: Union[str, List[str]]
    
    # API Configuration
    api_host: str
    api_port: int
    debug: bool
    
    # External Services
    email_service_url: str
    quote_notification_email: str
    
    @field_validator('cors_allow_methods', 'cors_allow_headers', mode='before')
    @classmethod
    def parse_json_list(cls, v):
        """Parse JSON string to list if needed"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # If it's not valid JSON, split by comma as fallback
                return [item.strip() for item in v.split(',')]
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @property
    def cors_allow_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string to list"""
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = Settings()
