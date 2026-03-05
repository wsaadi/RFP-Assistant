"""Branding settings model."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class BrandingSettings(Base):
    """Global application branding settings (single-row table)."""

    __tablename__ = "branding_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    app_name: Mapped[str] = mapped_column(String(255), default="RFP Assistant")
    logo_filename: Mapped[str] = mapped_column(String(500), default="")
    favicon_filename: Mapped[str] = mapped_column(String(500), default="")
    primary_color: Mapped[str] = mapped_column(String(20), default="#1B3A5C")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
