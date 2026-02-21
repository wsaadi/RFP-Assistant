"""Document models for file management and indexing."""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Enum as SAEnum, BigInteger, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class DocumentCategory(str, enum.Enum):
    OLD_RFP = "old_rfp"
    OLD_RESPONSE = "old_response"
    NEW_RFP = "new_rfp"


class FileType(str, enum.Enum):
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    XLSX = "xlsx"
    XLS = "xls"
    PPTX = "pptx"
    OTHER = "other"


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfp_projects.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[DocumentCategory] = mapped_column(
        SAEnum(DocumentCategory, name="document_category"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[FileType] = mapped_column(
        SAEnum(FileType, name="file_type"), nullable=False
    )
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SAEnum(ProcessingStatus, name="processing_status"),
        default=ProcessingStatus.PENDING,
    )
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    project = relationship("RFPProject", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    images = relationship("DocumentImage", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    anonymized_content: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding_id: Mapped[str] = mapped_column(String(255), default="")
    page_number: Mapped[int] = mapped_column(Integer, default=0)
    section_title: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    document = relationship("Document", back_populates="chunks")


class DocumentImage(Base):
    __tablename__ = "document_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    stored_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    page_number: Mapped[int] = mapped_column(Integer, default=0)
    context: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[dict] = mapped_column(JSON, default=list)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    document = relationship("Document", back_populates="images")
