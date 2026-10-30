"""Document lifecycle vocabulary; stored does not imply OCR completion."""
from enum import StrEnum


class ProcessingStatus(StrEnum):
    STORED = 'stored'
    QUEUED = 'queued'
    PROCESSING = 'processing'
    READY = 'ready'
    FAILED = 'failed'


class ArchiveError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)
