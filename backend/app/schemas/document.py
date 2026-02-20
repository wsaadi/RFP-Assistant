"""Document schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    project_id: str
    category: str
    original_filename: str
    file_type: str
    file_size: int
    processing_status: str
    page_count: int
    chunk_count: int
    uploaded_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentChunkOut(BaseModel):
    id: str
    document_id: str
    chunk_index: int
    content: str
    page_number: int
    section_title: str

    model_config = {"from_attributes": True}


class DocumentImageOut(BaseModel):
    id: str
    document_id: str
    stored_filename: str
    description: str
    page_number: int
    context: str
    tags: list
    width: int
    height: int

    model_config = {"from_attributes": True}


class AnonymizationMappingOut(BaseModel):
    id: str
    entity_type: str
    original_value: str
    anonymized_value: str
    is_active: bool

    model_config = {"from_attributes": True}


class SearchRequest(BaseModel):
    query: str
    category: Optional[str] = None
    top_k: int = 10


class SearchResult(BaseModel):
    chunk_id: str
    content: str
    document_name: str
    category: str
    page_number: int
    score: float


class StatisticsOut(BaseModel):
    total_pages: int = 0
    total_words: int = 0
    total_characters: int = 0
    anonymized_entities: int = 0
    chapters_completed: int = 0
    chapters_total: int = 0
    chapters_in_progress: int = 0
    documents_count: int = 0
    images_count: int = 0
    completion_percentage: float = 0.0


class ExportMetadata(BaseModel):
    project_name: str
    exported_at: str
    version: str = "1.0"
