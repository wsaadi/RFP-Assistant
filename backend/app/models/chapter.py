"""Chapter model for response structure."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Enum as SAEnum, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class ChapterType(str, enum.Enum):
    CHAPTER = "chapter"
    SUB_CHAPTER = "sub_chapter"
    ANNEXE = "annexe"
    DOCUMENT_TO_PROVIDE = "document_to_provide"


class ChapterStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    VALIDATED = "validated"


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfp_projects.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chapter_type: Mapped[ChapterType] = mapped_column(
        SAEnum(ChapterType, name="chapter_type"), default=ChapterType.CHAPTER
    )
    content: Mapped[str] = mapped_column(Text, default="")
    anonymized_content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ChapterStatus] = mapped_column(
        SAEnum(ChapterStatus, name="chapter_status"), default=ChapterStatus.NOT_STARTED
    )
    notes: Mapped[dict] = mapped_column(JSON, default=list)
    improvement_axes: Mapped[dict] = mapped_column(JSON, default=list)
    source_references: Mapped[dict] = mapped_column(JSON, default=list)
    image_references: Mapped[dict] = mapped_column(JSON, default=list)
    rfp_requirement: Mapped[str] = mapped_column(Text, default="")
    is_prefilled: Mapped[bool] = mapped_column(Boolean, default=False)
    numbering: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project = relationship("RFPProject", back_populates="chapters")
    children = relationship(
        "Chapter",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="Chapter.order",
    )
    parent = relationship("Chapter", back_populates="children", remote_side=[id])
