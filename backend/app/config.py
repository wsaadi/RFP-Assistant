"""Configuration settings for the application."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""

    app_name: str = "RFP Response Assistant"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://rfp_user:rfp_secret_password@db:5432/rfp_assistant"

    # JWT
    secret_key: str = "change-this-to-a-very-long-random-secret-key-in-production"
    access_token_expire_minutes: int = 480
    algorithm: str = "HS256"

    # File storage
    upload_dir: str = "/app/data/uploads"
    export_dir: str = "/app/data/exports"
    images_dir: str = "/app/data/images"

    # ChromaDB
    chroma_persist_dir: str = "/app/data/chroma"

    # Embedding model
    embedding_model: str = "intfloat/multilingual-e5-base"

    # GLiNER model
    gliner_model: str = "urchade/gliner_multi-v2.1"

    # HuggingFace
    hf_token: Optional[str] = None

    # Admin defaults
    admin_email: str = "admin@rfp-assistant.fr"
    admin_password: str = "admin123"

    # CORS
    cors_origins: str = "http://localhost,http://localhost:80,http://localhost:4200"

    # Rate limiting
    rate_limit: str = "60/minute"

    class Config:
        env_file = ".env"


settings = Settings()
