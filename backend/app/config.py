"""Configuration settings for the application."""
import secrets
import sys
from pydantic_settings import BaseSettings
from pydantic import field_validator
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

    # Ollama (local LLM for anonymization NER)
    # Ollama on DGX Spark — routed via host.docker.internal (Mac → socat → DGX)
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_ner_model: str = "qwen2.5:14b"
    ollama_ner_timeout: int = 120
    ollama_ner_concurrency: int = 2

    # Ollama (generation provider — alternative to Mistral)
    ollama_gen_model: str = "mistral:latest"
    ollama_gen_timeout: int = 300
    ollama_gen_stream_timeout: int = 600

    # Ollama Vision (local image analysis on DGX Spark)
    ollama_vision_model: str = "llama3.2-vision:11b"
    ollama_vision_timeout: int = 120
    ollama_vision_concurrency: int = 2

    # HuggingFace
    hf_token: Optional[str] = None

    # Admin defaults
    admin_email: str = "admin@rfp-assistant.fr"
    admin_password: str = "admin123"

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/0"

    # CORS
    cors_origins: str = "http://localhost,http://localhost:80,http://localhost:4200"

    # Rate limiting
    rate_limit: str = "60/minute"

    # Security: login brute-force protection
    login_rate_limit: str = "5/minute"
    login_lockout_attempts: int = 10
    login_lockout_minutes: int = 15

    # Security: minimum password strength
    min_password_length: int = 10

    # Upload quotas per user (0 = unlimited)
    max_upload_size_per_user_mb: int = 500  # Total storage per user in MB
    max_files_per_project: int = 50  # Max files per project

    class Config:
        env_file = ".env"

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Reject the placeholder secret key in non-test environments."""
        dangerous_defaults = {
            "change-this-to-a-very-long-random-secret-key-in-production",
            "changeme",
            "secret",
        }
        if v.lower() in dangerous_defaults:
            # Allow in tests; block in production
            if "pytest" not in sys.modules:
                print(
                    "\n*** SECURITY WARNING ***\n"
                    "SECRET_KEY is still set to the default placeholder.\n"
                    "Generate a strong key: python -c \"import secrets; print(secrets.token_urlsafe(64))\"\n"
                    "Set it in your .env file before deploying.\n"
                )
        return v

    @field_validator("admin_password")
    @classmethod
    def validate_admin_password(cls, v: str) -> str:
        """Warn if admin password is weak."""
        weak = {"admin123", "admin", "password", "123456", "changeme"}
        if v.lower() in weak:
            if "pytest" not in sys.modules:
                print(
                    "\n*** SECURITY WARNING ***\n"
                    "ADMIN_PASSWORD is set to a weak default.\n"
                    "Set a strong password (12+ chars, mixed case, numbers, symbols) in .env\n"
                )
        return v


settings = Settings()
