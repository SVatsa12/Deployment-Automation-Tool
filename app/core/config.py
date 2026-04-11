import json
from typing import Annotated, Any, List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    """
    Application configuration settings.
    All fields can be overridden via environment variables or a .env file.

    FIX 1: Replaced deprecated inner `class Config` with `model_config` dict
            (pydantic-settings v2 style).
    FIX 2: Removed case_sensitive=True — it breaks env-var resolution on Windows
            because Windows env vars are inherently case-insensitive.
    FIX 3: LOG_FILE now defaults to None so the app doesn't silently write log
            files to disk in every environment unless explicitly configured.
    FIX 4: Added CORS and worker/timeout settings needed by routes.py & engine.
    """

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    APP_NAME: str = "Deployment Automation Tool"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    DATABASE_URL: str = "sqlite:///./deployment.db"
    # When False (default), SQL is not printed on every request — avoids looking
    # "stuck" or broken due to ROLLBACK lines after read-only API calls.
    SQLALCHEMY_ECHO: bool = False

    # ------------------------------------------------------------------
    # Server
    # ------------------------------------------------------------------
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # FIX 4: CORS origins — restrict in production via the .env file
    # e.g.  ALLOWED_ORIGINS=https://mydomain.com,https://app.mydomain.com
    ALLOWED_ORIGINS: Annotated[List[str], NoDecode] = ["*"]

    # ------------------------------------------------------------------
    # Workflow / engine settings
    # ------------------------------------------------------------------
    DEFAULT_MAX_RETRIES: int = 3
    WORKFLOW_TIMEOUT_SECONDS: int = 3600   # 1 hour

    # FIX 4: How long (seconds) a background deployment task may run before
    # being considered hung. Should be <= WORKFLOW_TIMEOUT_SECONDS.
    DEPLOY_STEP_TIMEOUT_SECONDS: int = 300  # 5 minutes (matches subprocess timeout)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    LOG_LEVEL: str = "INFO"

    # FIX 3: Default None — opt-in to file logging via .env LOG_FILE=automation.log
    LOG_FILE: Optional[str] = None

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}, got '{v}'")
        return upper

    @field_validator("PORT")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"PORT must be between 1 and 65535, got {v}")
        return v

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: Any) -> List[str]:
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]

        if isinstance(v, str):
            value = v.strip()
            if not value:
                return ["*"]

            # Accept JSON list syntax from env, e.g. '["https://a.com"]'.
            if value.startswith("["):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "ALLOWED_ORIGINS JSON list is invalid. "
                        "Use formats like '*' or 'https://a.com,https://b.com' or '[\"https://a.com\"]'."
                    ) from exc

            # Accept comma-separated syntax and wildcard '*'.
            return [item.strip() for item in value.split(",") if item.strip()]

        raise ValueError("ALLOWED_ORIGINS must be a list or string")

    # ------------------------------------------------------------------
    # FIX 1 & 2: pydantic-settings v2 config — no inner class Config
    # ------------------------------------------------------------------
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        # case_sensitive intentionally omitted (defaults to False) so env
        # vars resolve correctly on both Windows and Linux.
    }


settings = Settings()