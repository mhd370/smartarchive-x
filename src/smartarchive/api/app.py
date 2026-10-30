"""Local document archive API. Run uvicorn with --app-dir src."""
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from smartarchive.config import Settings
from smartarchive.domain.documents import ArchiveError, ProcessingStatus
from smartarchive.persistence.database import Database
from smartarchive.persistence.storage import OriginalStore
from smartarchive.services.documents import Documents, public_record
from .middleware import UploadLimitMiddleware
from .schemas import Document, DocumentList, Statistics


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.storage_dir / 'archive.sqlite3')
    originals = OriginalStore(settings)
    documents = Documents(db, originals)

    @asynccontextmanager
    async def lifespan(app):
        originals.initialize()
        db.initialize()
        yield

    api = FastAPI(title='SmartArchive-X', version='0.5.0', lifespan=lifespan)
    api.state.documents, api.state.settings = documents, settings
    api.add_middleware(UploadLimitMiddleware, max_bytes=settings.max_upload_bytes + 1024 * 1024,
                       allowed_origins=settings.allowed_origins)
    api.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins),
                       allow_methods=['GET', 'POST'], allow_headers=['Content-Type'],
                       expose_headers=['Content-Disposition', 'ETag'])

    @api.exception_handler(ArchiveError)
    async def archive_error(request, exc):
        return JSONResponse({'detail': exc.message, 'code': exc.code}, status_code=exc.status)

    @api.get('/api/health')
    def health():
        db.statistics()
        return {'status': 'ok', 'ocr_configured': False,
                'max_upload_bytes': settings.max_upload_bytes,
                'supported_extensions': ['pdf', 'png', 'jpg', 'jpeg', 'webp', 'tif', 'tiff']}

    @api.get('/api/statistics', response_model=Statistics)
    def statistics():
        return db.statistics()

    @api.post('/api/documents', response_model=Document, status_code=201)
    def upload(file: Annotated[UploadFile, File()]):
        try:
            return documents.ingest(file.file, file.filename, file.content_type)
        finally:
            file.file.close()

    @api.get('/api/documents', response_model=DocumentList)
    def listing(q: str = Query('', max_length=200), status: ProcessingStatus | None = None,
                kind: Literal['pdf', 'image'] | None = None,
                limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=1_000_000)):
        result = db.list(q, status.value if status else None, kind, limit, offset)
        result['items'] = [public_record(row) for row in result['items']]
        return result

    @api.get('/api/documents/{document_id}', response_model=Document)
    def detail(document_id: UUID):
        record = documents.get(str(document_id))
        db.event(record['id'], 'document.viewed')
        return public_record(record)

    @api.get('/api/documents/{document_id}/status')
    def processing(document_id: UUID):
        record = documents.get(str(document_id))
        return {'document_id': record['id'], 'status': record['status'], 'reason': record['status_reason'],
                'updated_at': record['updated_at'], 'ocr_configured': False,
                'extracted_text': None, 'ocr_confidence': None, 'classification': None}

    @api.get('/api/documents/{document_id}/audit')
    def audit(document_id: UUID):
        documents.get(str(document_id))
        return {'items': db.events(str(document_id))}

    def original(document_id: UUID, inline: bool):
        record = documents.get(str(document_id))
        path = originals.verified_path(record)
        db.event(record['id'], 'document.previewed' if inline else 'document.downloaded')
        return FileResponse(path, media_type=record['mime_type'], filename=record['filename'],
                            content_disposition_type='inline' if inline else 'attachment',
                            headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store',
                                     'ETag': '"' + record['sha256'] + '"',
                                     'Content-Security-Policy': "default-src 'none'; sandbox"})

    @api.get('/api/documents/{document_id}/download')
    def download(document_id: UUID):
        return original(document_id, False)

    @api.get('/api/documents/{document_id}/content')
    def content(document_id: UUID):
        return original(document_id, True)

    @api.get('/api/documents/{document_id}/preview')
    def preview(document_id: UUID, page: int = Query(1, ge=1, le=settings.max_pages)):
        record = documents.get(str(document_id))
        data = originals.preview(record, page)
        db.event(record['id'], 'document.previewed', {'derivative': 'page_png', 'page': page})
        return Response(data, media_type='image/png', headers={'X-Content-Type-Options': 'nosniff',
                                                              'Cache-Control': 'no-store'})

    return api


app = create_app()
