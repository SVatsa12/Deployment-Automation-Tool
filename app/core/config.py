from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """
    Application configuration settings.
    Can be overridden by environment variables.
    """
    
    # Application
    APP_NAME: str = "Deployment Automation Tool"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = "sqlite:///./deployment.db"
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Workflow Settings
    DEFAULT_MAX_RETRIES: int = 3
    WORKFLOW_TIMEOUT_SECONDS: int = 3600  # 1 hour
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: Optional[str] = "automation.log"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
