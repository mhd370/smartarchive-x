"""Ingestion and original retrieval; never invents OCR text or confidence."""
import logging

from smartarchive.domain.documents import ArchiveError
from smartarchive.persistence.database import Database, now
from smartarchive.persistence.storage import OriginalStore, safe_filename

log = logging.getLogger(__name__)


def public_record(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != 'storage_key'}


class Documents:
    def __init__(self, db: Database, store: OriginalStore):
        self.db, self.store = db, store

    def ingest(self, stream, filename: str | None, declared_mime: str | None) -> dict:
        record = self.store.save(stream, safe_filename(filename), declared_mime)
        time = now()
        record.update(status='stored', status_reason='OCR_NOT_CONFIGURED', created_at=time, updated_at=time)
        try:
            self.db.insert(record)
        except Exception:
            # Retain a published original on DB failure for manual reconciliation;
            # never risk deleting an original after an ambiguous commit outcome.
            log.exception('Metadata transaction failed for original %s; reconcile storage', record['id'])
            raise ArchiveError('storage_error', 'تعذر تسجيل المستند. تحقق من الخدمة قبل إعادة المحاولة.', 503)
        return public_record(record)

    def get(self, document_id: str) -> dict:
        record = self.db.get(document_id)
        if not record:
            raise ArchiveError('not_found', 'المستند غير موجود.', 404)
        return record
