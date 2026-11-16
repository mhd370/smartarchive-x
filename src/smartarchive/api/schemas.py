"""Public response models exclude storage paths and unmeasured OCR fields."""
from datetime import datetime
from pydantic import BaseModel, Field
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
    category_id: str | None = None
    category_name: str | None = None
    category_state: str | None = None
    folder_id: str | None = None
    folder_path: str | None = None


class DocumentList(BaseModel):
    items: list[Document]
    total: int
    limit: int
    offset: int


class Statistics(BaseModel):
    total_documents: int
    total_bytes: int
    by_status: dict[ProcessingStatus, int]
    pages_pending_review: int = 0
    pages_reviewed: int = 0
    classification: dict[str, int] = Field(default_factory=dict)
    relations: dict[str, dict[str, int]] = Field(default_factory=dict)
    categories: list[dict] = Field(default_factory=list)


class Credentials(BaseModel):
    username: str
    password: str


class SetupRequest(Credentials):
    display_name: str
    setup_token: str | None = None


class UserCreate(SetupRequest):
    role: str


class UserUpdate(BaseModel):
    role: str | None = None
    active: bool | None = None
    display_name: str | None = None
    password: str | None = None


class PageRevision(BaseModel):
    text: str
    expected_version: int
    note: str = ''


class CategoryCreate(BaseModel):
    id: str
    name: str
    description: str = ''
    keywords: list[str]
    group_id: str | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    active: bool | None = None
    group_id: str | None = None


class ClassificationDecision(BaseModel):
    category_id: str
    expected_sequence: int
    reason: str = ''


class ReclassificationDismissal(BaseModel):
    suggestion_id: str
    reason: str = ''


class FolderCreate(BaseModel):
    name: str
    parent_id: str | None = None


class FolderAssign(BaseModel):
    folder_id: str | None = None


class MetadataEdit(BaseModel):
    value: str | None = None


class RelationReview(BaseModel):
    status: str
