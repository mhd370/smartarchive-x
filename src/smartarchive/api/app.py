"""Local document archive API. Run uvicorn with --app-dir src."""
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from smartarchive.config import Settings
from smartarchive.domain.documents import ArchiveError, ProcessingStatus
from smartarchive.persistence.database import Database
from smartarchive.persistence.storage import OriginalStore
from smartarchive.processing.pipeline import OcrService, Worker
from smartarchive.search.pages import PageTexts
from smartarchive.classification.service import Classifications
from smartarchive.enrichment.duplicates import Relations
from smartarchive.enrichment.metadata import Metadata
from smartarchive.operations import evaluation
from smartarchive.operations.backup import Backups, integrity
from smartarchive.services.auth import Accounts, can
from smartarchive.services.documents import Documents, public_record
from smartarchive.services.folders import Folders
from .middleware import UploadLimitMiddleware
from .schemas import (CategoryCreate, CategoryUpdate, ClassificationDecision, Credentials, Document, DocumentList,
                      FolderAssign, FolderCreate, MetadataEdit, PageRevision, ReclassificationDismissal,
                      RelationReview, SetupRequest, Statistics, UserCreate, UserUpdate)

COOKIE = 'sa_session'


def create_app(settings: Settings | None = None, engine_factory=None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.storage_dir / 'archive.sqlite3')
    originals = OriginalStore(settings)
    documents = Documents(db, originals)
    accounts = Accounts(db, settings.session_hours)
    texts = PageTexts(db)
    ocr = OcrService(db, originals, settings, engine_factory, texts)
    classes = Classifications(db, models_dir=settings.storage_dir / 'models')
    backups = Backups(settings.storage_dir, settings.backup_dir, '0.14.0')
    folders = Folders(db)
    metadata = Metadata(db)
    relations = Relations(db, metadata)

    def after_text_change(document_id: str, actor: str = 'system:enrichment', trigger: str = 'auto'):
        """New or corrected text is new evidence: re-extract metadata, re-suggest the category, re-check relations.
        Each step is isolated; none can fail the OCR run or the reviewer's save."""
        metadata.run_quietly(document_id)
        classes.suggest_quietly(document_id, actor if trigger == 'review' else 'system:classifier', trigger)
        relations.detect_quietly(document_id)

    ocr.on_ready = after_text_change
    worker = Worker(ocr)

    @asynccontextmanager
    async def lifespan(app):
        originals.initialize()
        db.initialize()
        texts.ensure_indexed()
        classes.seed()
        classes.ensure_suggested()
        with db.connect() as connection:  # one-time backfill for archives older than Sprint 5
            pending = [row[0] for row in connection.execute(
                'SELECT DISTINCT document_id FROM page_texts t WHERE NOT EXISTS'
                ' (SELECT 1 FROM metadata_values m WHERE m.document_id=t.document_id)')]
        for document_id in pending:
            metadata.run_quietly(document_id)
        relations.ensure_fingerprinted()
        if settings.ocr_worker:
            worker.start()
        yield
        worker.stop()

    api = FastAPI(title='SmartArchive-X', version='0.14.0', lifespan=lifespan)
    api.state.documents, api.state.settings, api.state.ocr, api.state.accounts = documents, settings, ocr, accounts
    api.state.texts, api.state.classes = texts, classes
    api.state.folders, api.state.metadata, api.state.relations = folders, metadata, relations
    api.add_middleware(UploadLimitMiddleware, max_bytes=settings.max_upload_bytes + 1024 * 1024,
                       allowed_origins=settings.allowed_origins)
    api.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_credentials=True,
                       allow_methods=['GET', 'POST', 'PATCH', 'PUT'], allow_headers=['Content-Type'],
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
        return {**db.statistics(), 'pages_pending_review': queue['total'], 'pages_reviewed': queue['reviewed_pages'],
                'classification': classes.summary(), 'relations': relations.summary(),
                'categories': [{'id': c['id'], 'name': c['name'], 'confirmed': c['confirmed'], 'suggested': c['suggested']}
                               for c in classes.categories() if c['active'] or c['confirmed'] or c['suggested']]}

    @api.post('/api/documents', response_model=Document, status_code=201)
    def upload(file: Annotated[UploadFile, File()], user: Uploader,
               folder_id: Annotated[str | None, Form(max_length=40)] = None):
        if folder_id:
            folders.get(folder_id)  # refuse an unknown folder before storing anything
        configured = ocr.info()['configured']
        reason = 'OCR_NOT_REQUESTED' if configured else 'OCR_NOT_CONFIGURED'
        try:
            record = documents.ingest(file.file, file.filename, file.content_type, user['username'], reason)
        finally:
            file.file.close()
        if folder_id:
            folders.file(record['id'], folder_id, user['username'])
        relations.detect_quietly(record['id'])  # exact duplicates are known before any OCR
        if configured and settings.ocr_auto:
            ocr.enqueue(documents.get(record['id']), user['username'], 'upload')
            return with_folder(public_record(documents.get(record['id'])))
        return with_folder(record)

    @api.get('/api/documents', response_model=DocumentList)
    def listing(user: Reader, q: str = Query('', max_length=200), status: ProcessingStatus | None = None,
                kind: Literal['pdf', 'image'] | None = None,
                category: str | None = Query(None, max_length=40), folder: str | None = Query(None, max_length=40),
                limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=1_000_000)):
        result = db.list(q, status.value if status else None, kind, limit, offset, category, folder)
        result['items'] = [public_record(row) for row in result['items']]
        return result

    @api.get('/api/documents/{document_id}', response_model=Document)
    def detail(document_id: UUID, user: Reader):
        record = documents.get(str(document_id))
        db.event(record['id'], 'document.viewed', actor=user['username'])
        return with_folder(public_record(record))

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
               category: str | None = Query(None, max_length=40),
               limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100_000),
               mode: Literal['ranked', 'exact'] = 'ranked'):
        """ranked (default): relevance order, tolerant of OCR errors and missing words; exact: every word present."""
        allowed = classes.documents_in(category) if category else None
        run = texts.search_ranked if mode == 'ranked' else texts.search
        return run(q, limit, offset, allowed=allowed)

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
        result = texts.revise(record, page, body.text, body.expected_version, body.note, user['username'])
        after_text_change(record['id'], user['username'], 'review')  # corrected text is new evidence
        return result

    # -- folders, metadata and relations (Sprint 5) ----------------------------------------------
    def with_folder(record: dict) -> dict:
        folder = folders.of(record['id'])
        return {**record, 'folder_id': folder['id'] if folder else None, 'folder_path': folder['path'] if folder else None}

    @api.get('/api/folders')
    def folder_tree(user: Reader):
        return {'items': folders.tree()}

    @api.post('/api/folders', status_code=201)
    def folder_create(body: FolderCreate, user: Uploader):
        return folders.create(body.name, body.parent_id, user['username'])

    @api.patch('/api/documents/{document_id}/folder')
    def document_folder(document_id: UUID, body: FolderAssign, user: Uploader):
        record = documents.get(str(document_id))
        folders.file(record['id'], body.folder_id, user['username'])
        return with_folder(public_record(record))

    @api.get('/api/documents/{document_id}/metadata')
    def document_metadata(document_id: UUID, user: Reader):
        return metadata.get(documents.get(str(document_id))['id'])

    @api.put('/api/documents/{document_id}/metadata/{field}')
    def document_metadata_edit(document_id: UUID, field: str, body: MetadataEdit, user: Reviewer):
        record = documents.get(str(document_id))
        result = metadata.edit(record['id'], field, body.value, user['username'])
        classes.suggest_quietly(record['id'], user['username'], 'metadata')
        relations.detect_quietly(record['id'])
        return result

    @api.get('/api/documents/{document_id}/relations')
    def document_relations(document_id: UUID, user: Reader):
        return {'items': relations.of(documents.get(str(document_id))['id'])}

    @api.post('/api/relations/{relation_id}/review')
    def relation_review(relation_id: UUID, body: RelationReview, user: Reviewer):
        return relations.review(str(relation_id), body.status, user['username'])

    @api.get('/api/category-groups')
    def category_groups(user: Reader):
        return {'items': classes.groups()}

    # -- classification (Sprint 3) --------------------------------------------------------------
    @api.get('/api/categories')
    def categories(user: Reader):
        return {'items': classes.categories()}

    @api.post('/api/categories', status_code=201)
    def create_category(body: CategoryCreate, user: Admin):
        return classes.create_category(body.id, body.name, body.description, body.keywords, user['username'],
                                       body.group_id)

    @api.patch('/api/categories/{category_id}')
    def update_category(category_id: str, body: CategoryUpdate, user: Admin):
        return classes.update_category(category_id, user['username'], name=body.name, description=body.description,
                                       keywords=body.keywords, active=body.active, group_id=body.group_id)

    @api.get('/api/classification/queue')
    def classification_queue(user: Reviewer, limit: int = Query(25, ge=1, le=100),
                             offset: int = Query(0, ge=0, le=1_000_000)):
        return classes.queue(limit, offset)

    @api.get('/api/documents/{document_id}/classification')
    def classification(document_id: UUID, user: Reader):
        return classes.get(documents.get(str(document_id))['id'])

    @api.post('/api/documents/{document_id}/classification/suggest')
    def classification_suggest(document_id: UUID, user: Reviewer):
        record = documents.get(str(document_id))
        classes.suggest(record['id'], user['username'], 'manual', force=True)
        return classes.get(record['id'])

    @api.post('/api/documents/{document_id}/classification')
    def classification_decide(document_id: UUID, body: ClassificationDecision, user: Reviewer):
        record = documents.get(str(document_id))
        return classes.decide(record['id'], body.category_id, body.reason, body.expected_sequence, user['username'])

    # -- controlled reclassification (Sprint 9) -----------------------------------------------------
    @api.get('/api/classification/reclassification')
    def reclassification_queue(user: Reviewer, limit: int = Query(25, ge=1, le=100),
                               offset: int = Query(0, ge=0, le=1_000_000)):
        return classes.reclassification_queue(limit, offset)

    @api.post('/api/documents/{document_id}/classification/reclassification/dismiss')
    def reclassification_dismiss(document_id: UUID, body: ReclassificationDismissal, user: Reviewer):
        record = documents.get(str(document_id))
        return classes.dismiss(record['id'], body.suggestion_id, body.reason, user['username'])

    # -- operations and evaluation (Sprint 4) ----------------------------------------------------
    # -- learned classifier (Sprint 8) --------------------------------------------------------------
    @api.get('/api/classifier')
    def classifier_info(user: Reader):
        return classes.model_info()

    @api.post('/api/admin/classifier/train', status_code=201)
    def classifier_train(user: Admin):
        """Train on every confirmed category, then refresh all suggestions (decisions never change)."""
        card = classes.train(user['username'])
        with db.connect() as connection:
            accounts.security_event(connection, user['username'], 'classifier.trained', card['id'],
                                    {'examples': card['examples'], 'refreshed': card['refreshed_suggestions']})
        return card

    @api.get('/api/admin/backups')
    def backup_list(user: Admin):
        return {'items': backups.list(), 'directory': str(backups.dir)}

    @api.post('/api/admin/backups', status_code=201)
    def backup_create(user: Admin):
        return backups.create(user['username'])

    @api.post('/api/admin/backups/{name}/verify')
    def backup_verify(name: str, user: Admin):
        return backups.verify(name, user['username'])

    @api.get('/api/admin/backups/{name}/download')
    def backup_download(name: str, user: Admin):
        return FileResponse(backups.path(name), media_type='application/zip', filename=name,
                            headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

    @api.post('/api/admin/integrity')
    def integrity_check(user: Admin):
        return integrity(settings.storage_dir, user['username'])

    @api.get('/api/evaluation')
    def evaluation_report(user: Reviewer):
        return evaluation.report(db)

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
