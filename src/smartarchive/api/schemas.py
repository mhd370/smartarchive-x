"""Public response models exclude storage paths and unmeasured OCR fields."""
from datetime import datetime
from pydantic import BaseModel
from smartarchive.domain.documents import ProcessingStatus


class Document(BaseModel):
    id: str
    filename: str
    size_bytes: int
    mime_type: str
    sha256: str
    page_count: int
    status: ProcessingStatus
    status_reason: str
    created_at: datetime
    updated_at: datetime


class DocumentList(BaseModel):
    items: list[Document]
    total: int
    limit: int
    offset: int


class Statistics(BaseModel):
    total_documents: int
    total_bytes: int
    by_status: dict[ProcessingStatus, int]
