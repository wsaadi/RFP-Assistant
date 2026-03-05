"""ResponseDocument model – represents a deliverable expected by the RFP."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Enum as SAEnum, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class DocumentFormat(str, enum.Enum):
    DOCX = "docx"
    XLSX = "xlsx"
    PDF = "pdf"
    OTHER = "other"


class ContentType(str, enum.Enum):
    """Whether this deliverable is a document to write from scratch or a template to fill in."""
    REDACTION = "redaction"      # Full text document to write (mémoire technique, notes, etc.)
    COMPLETION = "completion"    # Template/form to fill in (BPU Excel, DC forms, etc.)


class ResponseDocument(Base):
    __tablename__ = "response_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfp_projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    expected_format: Mapped[DocumentFormat] = mapped_column(
        SAEnum(DocumentFormat, name="document_format"), default=DocumentFormat.DOCX
    )
    content_type: Mapped[str] = mapped_column(
        SAEnum(ContentType, name="content_type"),
        default=ContentType.REDACTION,
        comment="redaction = write from scratch, completion = fill in existing template",
    )
    is_selected: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rfp_source: Mapped[str] = mapped_column(
        Text, default="",
        comment="Citation or reference from the RFP requiring this document",
    )
    fill_content: Mapped[str] = mapped_column(
        Text, default="",
        comment="AI-generated fill-in content/instructions for completion-type documents",
    )
    fill_status: Mapped[str] = mapped_column(
        String(50), default="pending",
        comment="pending | generating | completed | error",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project = relationship("RFPProject", back_populates="response_documents")
    chapters = relationship(
        "Chapter",
        back_populates="response_document",
        passive_deletes=True,
        order_by="Chapter.order",
    )
