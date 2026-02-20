"""Configuration settings for the application."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""

    app_name: str = "UTC Internship Report Assistant"
    debug: bool = False

    # API Keys (configured by user at runtime)
    openai_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None

    # Default AI provider
    default_ai_provider: str = "openai"

    class Config:
        env_file = ".env"


settings = Settings()
