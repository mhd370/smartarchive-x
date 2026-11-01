"""Local document archive API. Run uvicorn with --app-dir src."""
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, File, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from smartarchive.config import Settings
from smartarchive.domain.documents import ArchiveError, ProcessingStatus
from smartarchive.persistence.database import Database
from smartarchive.persistence.storage import OriginalStore
from smartarchive.processing.pipeline import OcrService, Worker
from smartarchive.search.pages import PageTexts
from smartarchive.services.auth import Accounts, can
from smartarchive.services.documents import Documents, public_record
from .middleware import UploadLimitMiddleware
from .schemas import (Credentials, Document, DocumentList, PageRevision, SetupRequest, Statistics, UserCreate,
                      UserUpdate)

COOKIE = 'sa_session'


def create_app(settings: Settings | None = None, engine_factory=None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.storage_dir / 'archive.sqlite3')
    originals = OriginalStore(settings)
    documents = Documents(db, originals)
    accounts = Accounts(db, settings.session_hours)
    texts = PageTexts(db)
    ocr = OcrService(db, originals, settings, engine_factory, texts)
    worker = Worker(ocr)

    @asynccontextmanager
    async def lifespan(app):
        originals.initialize()
        db.initialize()
        texts.ensure_indexed()
        if settings.ocr_worker:
            worker.start()
        yield
        worker.stop()

    api = FastAPI(title='SmartArchive-X', version='0.7.0', lifespan=lifespan)
    api.state.documents, api.state.settings, api.state.ocr, api.state.accounts = documents, settings, ocr, accounts
    api.state.texts = texts
    api.add_middleware(UploadLimitMiddleware, max_bytes=settings.max_upload_bytes + 1024 * 1024,
                       allowed_origins=settings.allowed_origins)
    api.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_credentials=True,
                       allow_methods=['GET', 'POST', 'PATCH'], allow_headers=['Content-Type'],
                       expose_headers=['Content-Disposition', 'ETag'])

    @api.exception_handler(ArchiveError)
    async def archive_error(request, exc):
        return JSONResponse({'detail': exc.message, 'code': exc.code}, status_code=exc.status)

    # -- identity -----------------------------------------------------------------------------
    def current_user(request: Request) -> dict:
        user = accounts.user_for(request.cookies.get(COOKIE))
        if not user:
            raise ArchiveError('unauthenticated', 'انتهت الجلسة أو لم تسجّل الدخول. يرجى تسجيل الدخول.', 401)
        return user

    def require(permission: str):
        def dependency(user: Annotated[dict, Depends(current_user)]) -> dict:
            if not can(user, permission):
                raise ArchiveError('forbidden', 'ليست لديك صلاحية لهذا الإجراء.', 403)
            return user
        return dependency

    Reader = Annotated[dict, Depends(require('documents.read'))]
    Uploader = Annotated[dict, Depends(require('documents.upload'))]
    Operator = Annotated[dict, Depends(require('ocr.run'))]
    Admin = Annotated[dict, Depends(require('users.manage'))]
    Reviewer = Annotated[dict, Depends(require('review.write'))]

    def start_session(response: Response, token: str):
        response.set_cookie(COOKIE, token, httponly=True, samesite='lax', secure=settings.secure_cookies,
                            max_age=settings.session_hours * 3600, path='/')

    @api.get('/api/auth/status')
    def auth_status(request: Request):
        return {'setup_required': accounts.setup_required(),
                'authenticated': accounts.user_for(request.cookies.get(COOKIE)) is not None}

    @api.post('/api/auth/setup', status_code=201)
    def setup(body: SetupRequest, response: Response):
        accounts.create(body.username, body.password, body.display_name, 'admin', 'setup', only_if_empty=True)
        token, user = accounts.login(body.username, body.password)
        start_session(response, token)
        return user

    @api.post('/api/auth/login')
    def login(body: Credentials, response: Response):
        token, user = accounts.login(body.username, body.password)
        start_session(response, token)
        return user

    @api.post('/api/auth/logout', status_code=204)
    def logout(request: Request, response: Response):
        user = accounts.user_for(request.cookies.get(COOKIE))
        accounts.logout(request.cookies.get(COOKIE), user['username'] if user else 'anonymous')
        response.delete_cookie(COOKIE, path='/')

    @api.get('/api/auth/me')
    def me(user: Annotated[dict, Depends(current_user)]):
        return user

    @api.get('/api/users')
    def users(user: Admin):
        return {'items': accounts.list()}

    @api.post('/api/users', status_code=201)
    def create_user(body: UserCreate, user: Admin):
        return accounts.create(body.username, body.password, body.display_name, body.role, user['username'])

    @api.patch('/api/users/{user_id}')
    def update_user(user_id: UUID, body: UserUpdate, user: Admin):
        return accounts.update(str(user_id), user, role=body.role, active=body.active,
                               display_name=body.display_name, password=body.password)

    # -- documents ----------------------------------------------------------------------------
    @api.get('/api/health')
    def health():
        db.statistics()
        info = ocr.info()
        return {'status': 'ok', 'ocr_configured': info['configured'], 'ocr_engine': info['engine'],
                'ocr_languages': info['languages'],
                'max_upload_bytes': settings.max_upload_bytes,
                'supported_extensions': ['pdf', 'png', 'jpg', 'jpeg', 'webp', 'tif', 'tiff']}

    @api.get('/api/statistics', response_model=Statistics)
    def statistics(user: Reader):
        queue = texts.queue(1, 0)
        return {**db.statistics(), 'pages_pending_review': queue['total'], 'pages_reviewed': queue['reviewed_pages']}

    @api.post('/api/documents', response_model=Document, status_code=201)
    def upload(file: Annotated[UploadFile, File()], user: Uploader):
        configured = ocr.info()['configured']
        reason = 'OCR_NOT_REQUESTED' if configured else 'OCR_NOT_CONFIGURED'
        try:
            record = documents.ingest(file.file, file.filename, file.content_type, user['username'], reason)
        finally:
            file.file.close()
        if configured and settings.ocr_auto:
            ocr.enqueue(documents.get(record['id']), user['username'], 'upload')
            return public_record(documents.get(record['id']))
        return record

    @api.get('/api/documents', response_model=DocumentList)
    def listing(user: Reader, q: str = Query('', max_length=200), status: ProcessingStatus | None = None,
                kind: Literal['pdf', 'image'] | None = None,
                limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=1_000_000)):
        result = db.list(q, status.value if status else None, kind, limit, offset)
        result['items'] = [public_record(row) for row in result['items']]
        return result

    @api.get('/api/documents/{document_id}', response_model=Document)
    def detail(document_id: UUID, user: Reader):
        record = documents.get(str(document_id))
        db.event(record['id'], 'document.viewed', actor=user['username'])
        return public_record(record)

    def latest_ready(document_id: str) -> dict | None:
        return next((run for run in ocr.runs(document_id) if run['status'] == 'ready'), None)

    @api.get('/api/documents/{document_id}/status')
    def processing(document_id: UUID, user: Reader):
        record = documents.get(str(document_id))
        runs = ocr.runs(record['id'])
        ready = next((run for run in runs if run['status'] == 'ready'), None)
        return {'document_id': record['id'], 'status': record['status'], 'reason': record['status_reason'],
                'updated_at': record['updated_at'], 'ocr_configured': ocr.info()['configured'],
                'latest_run': runs[0] if runs else None,
                'extracted_text': ocr.text(ready['id']) if ready else None,
                'pending_review_pages': texts.pending(record['id']),
                'ocr_confidence': ready['mean_confidence'] if ready else None,
                'review_required': ready['review_required'] if ready else None,
                'classification': None}

    @api.get('/api/documents/{document_id}/ocr')
    def ocr_summary(document_id: UUID, user: Reader):
        record = documents.get(str(document_id))
        runs = ocr.runs(record['id'])
        shown = latest_ready(record['id']) or (runs[0] if runs else None)
        return {'engine': ocr.info(), 'runs': runs, 'run': shown, 'pages': ocr.pages(shown['id']) if shown else []}

    @api.post('/api/documents/{document_id}/ocr', status_code=201)
    def ocr_start(document_id: UUID, user: Operator):
        record = documents.get(str(document_id))
        return ocr.enqueue(record, user['username'], 'manual')

    @api.get('/api/documents/{document_id}/ocr/pages/{page}')
    def ocr_page(document_id: UUID, page: int, user: Reader, run_id: UUID | None = None):
        record = documents.get(str(document_id))
        if not 1 <= page <= record['page_count']:
            raise ArchiveError('page_not_found', 'الصفحة المطلوبة غير موجودة.', 404)
        run = ocr.run(str(run_id)) if run_id else latest_ready(record['id'])
        if not run or run['document_id'] != record['id']:
            raise ArchiveError('ocr_not_found', 'لا توجد نتائج OCR لهذه الصفحة بعد.', 404)
        analysis = next((item for item in ocr.pages(run['id']) if item['page_no'] == page), None)
        return {'run_id': run['id'], 'page': page, 'analysis': analysis, 'lines': ocr.lines(run['id'], page)}

    # -- search and review (Sprint 2) ------------------------------------------------------------
    @api.get('/api/search')
    def search(user: Reader, q: str = Query(..., min_length=1, max_length=200),
               limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100_000)):
        return texts.search(q, limit, offset)

    @api.get('/api/review/queue')
    def review_queue(user: Reviewer, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=1_000_000)):
        return texts.queue(limit, offset)

    @api.get('/api/documents/{document_id}/pages/{page}/text')
    def page_text(document_id: UUID, page: int, user: Reader):
        return texts.page(documents.get(str(document_id)), page)

    @api.get('/api/documents/{document_id}/pages/{page}/revisions/{version}')
    def page_revision(document_id: UUID, page: int, version: int, user: Reader):
        record = documents.get(str(document_id))
        return texts.revision_text(record['id'], page, version)

    @api.post('/api/documents/{document_id}/pages/{page}/text')
    def revise_page(document_id: UUID, page: int, body: PageRevision, user: Reviewer):
        record = documents.get(str(document_id))
        return texts.revise(record, page, body.text, body.expected_version, body.note, user['username'])

    @api.get('/api/documents/{document_id}/audit')
    def audit(document_id: UUID, user: Reader):
        documents.get(str(document_id))
        return {'items': db.events(str(document_id))}

    def original(document_id: UUID, inline: bool, user: dict):
        record = documents.get(str(document_id))
        path = originals.verified_path(record)
        db.event(record['id'], 'document.previewed' if inline else 'document.downloaded', actor=user['username'])
        return FileResponse(path, media_type=record['mime_type'], filename=record['filename'],
                            content_disposition_type='inline' if inline else 'attachment',
                            headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store',
                                     'ETag': '"' + record['sha256'] + '"',
                                     'Content-Security-Policy': "default-src 'none'; sandbox"})

    @api.get('/api/documents/{document_id}/download')
    def download(document_id: UUID, user: Reader):
        return original(document_id, False, user)

    @api.get('/api/documents/{document_id}/content')
    def content(document_id: UUID, user: Reader):
        return original(document_id, True, user)

    @api.get('/api/documents/{document_id}/preview')
    def preview(document_id: UUID, user: Reader, page: int = Query(1, ge=1, le=settings.max_pages)):
        record = documents.get(str(document_id))
        data = originals.preview(record, page)
        db.event(record['id'], 'document.previewed', {'derivative': 'page_png', 'page': page}, user['username'])
        return Response(data, media_type='image/png', headers={'X-Content-Type-Options': 'nosniff',
                                                              'Cache-Control': 'no-store'})

    return api


app = create_app()
