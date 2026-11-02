"""Effective page text, human review revisions, the review queue and text search.

- `page_revisions` is append-only: every correction is a new numbered version with its author.
- `page_texts` holds the text that search and the UI use for each page: the latest human revision
  if one exists, otherwise the OCR text of the latest completed run. It is derived data and can be
  rebuilt from `ocr_lines` and `page_revisions` at any time.
- Search compares normalized Arabic (see arabic.py) as substrings, so clitics such as و/ب/ال
  attached to a word still match. Results are grouped per document and ranked by occurrences.
"""
import uuid

from smartarchive.domain.documents import ArchiveError
from smartarchive.persistence.database import Database, now
from .arabic import find_spans, normalize, parse_query, snippets

MAX_TEXT = 100_000
MAX_NOTE = 500
SEARCH_ROW_CAP = 5000
LATEST_READY = '''SELECT r.id, r.document_id, r.finished_at FROM ocr_runs r WHERE r.status='ready'
    AND r.id = (SELECT id FROM ocr_runs WHERE document_id=r.document_id AND status='ready'
                ORDER BY created_at DESC, id LIMIT 1)'''


def _like(term: str) -> str:
    return '%' + term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


class PageTexts:
    def __init__(self, db: Database):
        self.db = db

    # -- indexing -----------------------------------------------------------------------------
    @staticmethod
    def _upsert(db, document_id: str, page_no: int, source: str, run_id: str | None, revision: int | None, text: str):
        db.execute('''INSERT INTO page_texts(document_id,page_no,source,run_id,revision,text,normalized,updated_at)
                      VALUES (?,?,?,?,?,?,?,?)
                      ON CONFLICT(document_id,page_no) DO UPDATE SET source=excluded.source, run_id=excluded.run_id,
                      revision=excluded.revision, text=excluded.text, normalized=excluded.normalized,
                      updated_at=excluded.updated_at''',
                   (document_id, page_no, source, run_id, revision, text, normalize(text), now()))

    def index_run(self, db, run_id: str, document_id: str):
        """Make a completed run's OCR text searchable, except on pages a person has already corrected."""
        reviewed = {row[0] for row in db.execute('SELECT DISTINCT page_no FROM page_revisions WHERE document_id=?',
                                                 (document_id,))}
        pages = [row[0] for row in db.execute('SELECT page_no FROM page_analyses WHERE run_id=? ORDER BY page_no',
                                              (run_id,))]
        for page_no in pages:
            if page_no in reviewed:
                continue
            lines = [row[0] for row in db.execute('SELECT text FROM ocr_lines WHERE run_id=? AND page_no=? ORDER BY line_no',
                                                  (run_id, page_no))]
            self._upsert(db, document_id, page_no, 'ocr', run_id, None, '\n'.join(lines))

    def ensure_indexed(self) -> int:
        """Index documents whose latest completed run predates this feature (one-time backfill)."""
        with self.db.connect() as db:
            runs = db.execute(LATEST_READY + ' AND NOT EXISTS (SELECT 1 FROM page_texts t WHERE t.run_id=r.id)').fetchall()
            for run in runs:
                self.index_run(db, run['id'], run['document_id'])
            return len(runs)

    # -- reading ------------------------------------------------------------------------------
    def pending_count(self, db, document_id: str) -> int:
        return db.execute(f'''SELECT COUNT(*) FROM page_analyses a JOIN ({LATEST_READY}) r ON a.run_id=r.id
            WHERE r.document_id=? AND a.review_required=1 AND NOT EXISTS (
            SELECT 1 FROM page_revisions v WHERE v.document_id=r.document_id AND v.page_no=a.page_no)''',
                          (document_id,)).fetchone()[0]

    def pending(self, document_id: str) -> int:
        with self.db.connect() as db:
            return self.pending_count(db, document_id)

    def page(self, document: dict, page_no: int) -> dict:
        self._check_page(document, page_no)
        with self.db.connect() as db:
            current = db.execute('SELECT * FROM page_texts WHERE document_id=? AND page_no=?',
                                 (document['id'], page_no)).fetchone()
            revisions = db.execute('SELECT id,version,base_source,base_run_id,note,author,created_at,length(text) AS characters'
                                   ' FROM page_revisions WHERE document_id=? AND page_no=? ORDER BY version DESC',
                                   (document['id'], page_no)).fetchall()
            analysis = db.execute(f'''SELECT a.mean_confidence, a.review_required, a.blank, r.id AS run_id
                FROM page_analyses a JOIN ({LATEST_READY}) r ON a.run_id=r.id WHERE r.document_id=? AND a.page_no=?''',
                                  (document['id'], page_no)).fetchone()
        return {'document_id': document['id'], 'page_no': page_no,
                'available': current is not None,
                'source': current['source'] if current else None,
                'text': current['text'] if current else None,
                'run_id': current['run_id'] if current else (analysis['run_id'] if analysis else None),
                'version': revisions[0]['version'] if revisions else 0,
                'reviewed': bool(revisions),
                'ocr_confidence': analysis['mean_confidence'] if analysis else None,
                'review_required': bool(analysis['review_required']) if analysis else None,
                'blank': bool(analysis['blank']) if analysis else None,
                'revisions': [dict(row) for row in revisions]}

    def revision_text(self, document_id: str, page_no: int, version: int) -> dict:
        with self.db.connect() as db:
            row = db.execute('SELECT * FROM page_revisions WHERE document_id=? AND page_no=? AND version=?',
                             (document_id, page_no, version)).fetchone()
        if not row:
            raise ArchiveError('revision_not_found', 'نسخة المراجعة المطلوبة غير موجودة.', 404)
        return dict(row)

    # -- review -------------------------------------------------------------------------------
    @staticmethod
    def _check_page(document: dict, page_no: int):
        if not 1 <= page_no <= document['page_count']:
            raise ArchiveError('page_not_found', 'الصفحة المطلوبة غير موجودة.', 404)

    def revise(self, document: dict, page_no: int, text: str, expected_version: int, note: str, author: str) -> dict:
        self._check_page(document, page_no)
        text = text.replace('\r\n', '\n').strip()
        note = (note or '').strip()
        if len(text) > MAX_TEXT:
            raise ArchiveError('text_too_long', 'النص أطول من الحد المسموح للصفحة الواحدة.', 422)
        if len(note) > MAX_NOTE:
            raise ArchiveError('note_too_long', 'الملاحظة أطول من 500 حرف.', 422)
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            document = dict(db.execute('SELECT * FROM documents WHERE id=?', (document['id'],)).fetchone())
            if document['status'] != 'ready':
                raise ArchiveError('not_ready', 'لا يمكن مراجعة النص قبل اكتمال استخراجه.', 409)
            current = db.execute('SELECT * FROM page_texts WHERE document_id=? AND page_no=?',
                                 (document['id'], page_no)).fetchone()
            if current is None:
                raise ArchiveError('ocr_not_found', 'لا يوجد نص مستخرج لهذه الصفحة بعد.', 409)
            latest = db.execute('SELECT COALESCE(MAX(version),0) FROM page_revisions WHERE document_id=? AND page_no=?',
                                (document['id'], page_no)).fetchone()[0]
            if latest != expected_version:
                raise ArchiveError('stale_version',
                                   'عدّل شخص آخر هذه الصفحة بعد فتحك لها. أعد تحميل النص وراجع التعديل الأحدث.', 409)
            if text == current['text']:
                raise ArchiveError('unchanged', 'لم يتغير النص؛ لا حاجة لحفظ نسخة جديدة.', 422)
            revision = {'id': str(uuid.uuid4()), 'document_id': document['id'], 'page_no': page_no,
                        'version': latest + 1, 'base_source': current['source'], 'base_run_id': current['run_id'],
                        'text': text, 'note': note, 'author': author, 'created_at': now()}
            db.execute(f"INSERT INTO page_revisions ({','.join(revision)}) VALUES ({','.join('?' for _ in revision)})",
                       list(revision.values()))
            self._upsert(db, document['id'], page_no, 'review', current['run_id'], revision['version'], text)
            pending = self.pending_count(db, document['id'])
            if pending == 0 and document['status_reason'] == 'REVIEW_REQUIRED':
                self.db.set_status(db, document['id'], 'ready', 'REVIEW_COMPLETED')
            self.db._event(db, document['id'], 'page.reviewed',
                           {'page': page_no, 'version': revision['version'], 'characters': len(text),
                            'previous_characters': len(current['text']), 'base_source': current['source'],
                            'pending_pages': pending, 'note': note}, author)
        return self.page(self.db.get(document['id']), page_no)

    def queue(self, limit: int, offset: int) -> dict:
        query = f'''FROM page_analyses a JOIN ({LATEST_READY}) r ON a.run_id=r.id JOIN documents d ON d.id=r.document_id
            WHERE a.review_required=1 AND NOT EXISTS (
            SELECT 1 FROM page_revisions v WHERE v.document_id=r.document_id AND v.page_no=a.page_no)'''
        with self.db.connect() as db:
            total = db.execute('SELECT COUNT(*) ' + query).fetchone()[0]
            rows = db.execute('SELECT d.id AS document_id, d.filename, d.page_count, a.page_no, a.mean_confidence,'
                              ' a.quality_score, a.text_length, r.id AS run_id, r.finished_at ' + query +
                              ' ORDER BY a.mean_confidence IS NOT NULL, a.mean_confidence, r.finished_at, a.page_no'
                              ' LIMIT ? OFFSET ?', (limit, offset)).fetchall()
            reviewed = db.execute('SELECT COUNT(*) FROM (SELECT DISTINCT document_id, page_no FROM page_revisions)').fetchone()[0]
        return {'items': [dict(row) for row in rows], 'total': total, 'reviewed_pages': reviewed,
                'limit': limit, 'offset': offset}

    # -- search -------------------------------------------------------------------------------
    def search(self, query: str, limit: int, offset: int, pages_per_document: int = 5,
               allowed: set[str] | None = None) -> dict:
        """`allowed`, when given, limits results to these document ids (e.g. one category)."""
        terms = parse_query(query)
        if not terms:
            return {'query': query, 'terms': [], 'items': [], 'total': 0, 'limit': limit, 'offset': offset,
                    'truncated': False}
        where = ' AND '.join('t.normalized LIKE ? ESCAPE \'\\\'' for _ in terms)
        with self.db.connect() as db:
            rows = db.execute('SELECT t.document_id, t.page_no, t.source, t.revision, t.text FROM page_texts t'
                              f' WHERE {where} ORDER BY t.document_id, t.page_no LIMIT ?',
                              [*map(_like, terms), SEARCH_ROW_CAP + 1]).fetchall()
            documents = {row['id']: dict(row) for row in db.execute(
                'SELECT d.*, v.category_id, v.state AS category_state, c.name AS category_name FROM documents d'
                ' LEFT JOIN document_categories v ON v.document_id=d.id LEFT JOIN categories c ON c.id=v.category_id')}
        truncated = len(rows) > SEARCH_ROW_CAP
        hits: dict[str, dict] = {}
        for row in rows[:SEARCH_ROW_CAP]:
            spans = find_spans(row['text'], terms)
            entry = hits.setdefault(row['document_id'], {'pages': [], 'score': 0})
            entry['score'] += len(spans)
            entry['pages'].append({'page_no': row['page_no'], 'source': row['source'], 'revision': row['revision'],
                                   'match_count': len(spans), 'snippets': snippets(row['text'], spans)})
        for document_id, record in documents.items():
            name = normalize(record['filename'])
            if all(term in name for term in terms):
                entry = hits.setdefault(document_id, {'pages': [], 'score': 0})
                entry['filename_match'] = True
                entry['score'] += 5
        if allowed is not None:
            hits = {key: value for key, value in hits.items() if key in allowed}
        newest_first = sorted(hits.items(), key=lambda item: documents[item[0]]['created_at'], reverse=True)
        ranked = sorted(newest_first, key=lambda item: -item[1]['score'])
        items = []
        for document_id, entry in ranked[offset:offset + limit]:
            record = {k: v for k, v in documents[document_id].items() if k != 'storage_key'}
            pages = sorted(entry['pages'], key=lambda page: (-page['match_count'], page['page_no']))
            items.append({'document': record, 'score': entry['score'], 'filename_match': entry.get('filename_match', False),
                          'matched_pages': len(pages), 'pages': pages[:pages_per_document]})
        return {'query': query, 'terms': terms, 'items': items, 'total': len(ranked), 'limit': limit,
                'offset': offset, 'truncated': truncated}

