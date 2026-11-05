"""
Application configuration for the PINITHUB forensic service.

Environment variables are validated at startup via pydantic-settings.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    # Service port
    forensics_port: int = 8001

    # Logging level
    log_level: str = "info"

    # API URL for claiming analysis jobs (the Node API)
    api_url: str = "http://localhost:4000"

    # Worker configuration
    worker_enabled: bool = False
    worker_poll_interval_seconds: int = 5
    worker_max_concurrent_jobs: int = 1

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    """Returns a cached Settings instance."""
    if not hasattr(get_settings, "_cached"):
        get_settings._cached = Settings()  # type: ignore[attr-defined]
    return get_settings._cached  # type: ignore[attr-defined]
