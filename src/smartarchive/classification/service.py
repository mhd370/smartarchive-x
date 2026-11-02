"""Categories, classification suggestions and human decisions.

- `classifications` is append-only. A *suggestion* is written by the classifier (or nothing changes when
  the text and categories are the same as for the previous suggestion). A *decision* is written only by a
  person: confirming a suggestion, choosing another category, or reclassifying (a reason is required).
- The document's current category comes from the view `document_categories`: the latest decision, else
  the latest suggestion (state `suggested`, or `uncertain` when the classifier abstained).
"""
import hashlib
import json
import logging
import re
import uuid

from smartarchive.domain.documents import ArchiveError
from smartarchive.persistence.database import Database, now
from .classifier import DEFAULT_CATEGORIES, METHOD, Category, classify

log = logging.getLogger(__name__)
SYSTEM = 'system:classifier'
SLUG = re.compile(r'[a-z][a-z0-9_-]{1,39}')
MAX_KEYWORDS, MAX_KEYWORD_LEN = 60, 60


def _row(row) -> dict:
    item = dict(row)
    for key in ('scores', 'evidence', 'basis', 'keywords'):
        if key in item and item[key] is not None:
            item[key] = json.loads(item[key])
    if 'active' in item:
        item['active'] = bool(item['active'])
    return item


class Classifications:
    def __init__(self, db: Database, min_score: float = 3.0, min_confidence: float = 0.5):
        self.db, self.min_score, self.min_confidence = db, min_score, min_confidence

    # -- categories ---------------------------------------------------------------------------
    def seed(self):
        with self.db.connect() as db:
            if db.execute('SELECT COUNT(*) FROM categories').fetchone()[0]:
                return
            stamp = now()
            db.executemany('INSERT INTO categories(id,name,description,keywords,active,created_by,created_at,updated_at)'
                           ' VALUES (?,?,?,?,1,?,?,?)',
                           [(cid, name, desc, json.dumps(words, ensure_ascii=False), 'system', stamp, stamp)
                            for cid, name, desc, words in DEFAULT_CATEGORIES])

    def categories(self, include_inactive: bool = True) -> list[dict]:
        with self.db.connect() as db:
            rows = db.execute('''SELECT c.*,
                (SELECT COUNT(*) FROM document_categories v WHERE v.category_id=c.id AND v.state='confirmed') AS confirmed,
                (SELECT COUNT(*) FROM document_categories v WHERE v.category_id=c.id AND v.state='suggested') AS suggested
                FROM categories c ORDER BY c.active DESC, c.created_at, c.name''').fetchall()
        items = [_row(row) for row in rows]
        return items if include_inactive else [item for item in items if item['active']]

    @staticmethod
    def _clean_keywords(keywords: list[str]) -> list[str]:
        cleaned = []
        for word in keywords:
            word = ' '.join(str(word).split())
            if word and word not in cleaned:
                if len(word) > MAX_KEYWORD_LEN:
                    raise ArchiveError('keyword_too_long', 'الكلمة المفتاحية أطول من 60 حرفًا.', 422)
                cleaned.append(word)
        if not cleaned:
            raise ArchiveError('keywords_required', 'أضف كلمة مفتاحية واحدة على الأقل للفئة.', 422)
        if len(cleaned) > MAX_KEYWORDS:
            raise ArchiveError('too_many_keywords', 'الحد الأقصى 60 كلمة مفتاحية للفئة.', 422)
        return cleaned

    @staticmethod
    def _clean_name(name: str) -> str:
        name = ' '.join((name or '').split())
        if not 2 <= len(name) <= 60:
            raise ArchiveError('invalid_name', 'اسم الفئة يجب أن يكون بين 2 و60 حرفًا.', 422)
        return name

    def create_category(self, cid: str, name: str, description: str, keywords: list[str], actor: str) -> dict:
        if not SLUG.fullmatch(cid or ''):
            raise ArchiveError('invalid_id', 'المعرّف بأحرف إنجليزية صغيرة وأرقام (2–40)، ويبدأ بحرف.', 422)
        name, words = self._clean_name(name), self._clean_keywords(keywords)
        stamp = now()
        with self.db.connect() as db:
            if db.execute('SELECT 1 FROM categories WHERE id=? OR name=?', (cid, name)).fetchone():
                raise ArchiveError('duplicate_category', 'توجد فئة بالمعرّف أو الاسم نفسه.', 409)
            db.execute('INSERT INTO categories(id,name,description,keywords,active,created_by,created_at,updated_at)'
                       ' VALUES (?,?,?,?,1,?,?,?)', (cid, name, (description or '').strip()[:300],
                                                     json.dumps(words, ensure_ascii=False), actor, stamp, stamp))
            self._security(db, actor, 'category.created', cid, {'name': name, 'keywords': words})
        return self.category(cid)

    def update_category(self, cid: str, actor: str, name: str | None = None, description: str | None = None,
                        keywords: list[str] | None = None, active: bool | None = None) -> dict:
        current = self.category(cid)
        changes = {}
        if name is not None:
            changes['name'] = self._clean_name(name)
        if description is not None:
            changes['description'] = description.strip()[:300]
        if keywords is not None:
            changes['keywords'] = json.dumps(self._clean_keywords(keywords), ensure_ascii=False)
        if active is not None:
            changes['active'] = int(active)
        if not changes:
            return current
        with self.db.connect() as db:
            if 'name' in changes and db.execute('SELECT 1 FROM categories WHERE name=? AND id<>?',
                                                (changes['name'], cid)).fetchone():
                raise ArchiveError('duplicate_category', 'توجد فئة أخرى بالاسم نفسه.', 409)
            changes['updated_at'] = now()
            db.execute(f"UPDATE categories SET {','.join(f'{key}=?' for key in changes)} WHERE id=?",
                       [*changes.values(), cid])
            self._security(db, actor, 'category.updated', cid,
                           {key: (json.loads(value) if key == 'keywords' else value)
                            for key, value in changes.items() if key != 'updated_at'})
        return self.category(cid)

    def category(self, cid: str) -> dict:
        found = next((item for item in self.categories() if item['id'] == cid), None)
        if not found:
            raise ArchiveError('category_not_found', 'الفئة غير موجودة.', 404)
        return found

    @staticmethod
    def _security(db, actor, action, subject, details):
        db.execute('INSERT INTO security_events(actor,action,subject,timestamp,details) VALUES (?,?,?,?,?)',
                   (actor, action, subject, now(), json.dumps(details, ensure_ascii=False)))

    # -- suggestions --------------------------------------------------------------------------
    def _basis(self, db, document_id: str) -> tuple[str, dict, str]:
        rows = db.execute('SELECT page_no, source, run_id, revision, text FROM page_texts WHERE document_id=?'
                          ' ORDER BY page_no', (document_id,)).fetchall()
        text = '\n'.join(row['text'] for row in rows)
        stamp = db.execute('SELECT COALESCE(MAX(updated_at),\'\') FROM categories').fetchone()[0]
        digest = hashlib.sha256((text + '\x00' + stamp).encode()).hexdigest()
        basis = {'pages': len(rows), 'run_ids': sorted({row['run_id'] for row in rows if row['run_id']}),
                 'reviewed_pages': sum(1 for row in rows if row['source'] == 'review'),
                 'categories_updated_at': stamp, 'digest': digest}
        return text, basis, digest

    def suggest(self, document_id: str, actor: str = SYSTEM, trigger: str = 'auto', force: bool = False) -> dict | None:
        """Write a new suggestion unless nothing changed since the previous one (or `force`)."""
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            document = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
            if not document:
                raise ArchiveError('not_found', 'المستند غير موجود.', 404)
            text, basis, digest = self._basis(db, document_id)
            last = db.execute("SELECT basis FROM classifications WHERE document_id=? AND kind='suggestion'"
                              ' ORDER BY sequence DESC LIMIT 1', (document_id,)).fetchone()
            if last and not force and json.loads(last['basis']).get('digest') == digest:
                return None
            categories = [Category(row['id'], row['name'], json.loads(row['keywords'])) for row in
                          db.execute('SELECT * FROM categories WHERE active=1 ORDER BY id').fetchall()]
            result = classify(text, document['filename'], categories, self.min_score, self.min_confidence)
            record = {'id': str(uuid.uuid4()), 'document_id': document_id, 'kind': 'suggestion',
                      'category_id': result.category_id, 'confidence': result.confidence, 'method': METHOD,
                      'scores': json.dumps({k: v for k, v in result.candidates}, ensure_ascii=False),
                      'evidence': json.dumps(result.evidence, ensure_ascii=False),
                      'basis': json.dumps({**basis, 'trigger': trigger, 'outcome': result.reason}),
                      'reason': result.reason, 'actor': actor, 'created_at': now()}
            db.execute(f"INSERT INTO classifications ({','.join(record)}) VALUES ({','.join('?' for _ in record)})",
                       list(record.values()))
            # Suggestions are machine output kept in the classification history; the audit log records the
            # people who confirm or change a category.
        return record

    def suggest_quietly(self, document_id: str, actor: str = SYSTEM, trigger: str = 'auto'):
        """For automatic hooks: a classification problem must never break OCR or review."""
        try:
            self.suggest(document_id, actor, trigger)
        except Exception:
            log.exception('Classification suggestion failed for %s', document_id)

    def ensure_suggested(self) -> int:
        """Suggest for documents that have text but were never classified (archives older than this feature)."""
        with self.db.connect() as db:
            ids = [row[0] for row in db.execute(
                'SELECT DISTINCT t.document_id FROM page_texts t WHERE NOT EXISTS ('
                'SELECT 1 FROM classifications c WHERE c.document_id=t.document_id)').fetchall()]
        for document_id in ids:
            self.suggest_quietly(document_id, trigger='backfill')
        return len(ids)

    # -- decisions ----------------------------------------------------------------------------
    def decide(self, document_id: str, category_id: str, reason: str, expected_sequence: int, actor: str) -> dict:
        reason = ' '.join((reason or '').split())
        if len(reason) > 500:
            raise ArchiveError('reason_too_long', 'السبب أطول من 500 حرف.', 422)
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM documents WHERE id=?', (document_id,)).fetchone():
                raise ArchiveError('not_found', 'المستند غير موجود.', 404)
            category = db.execute('SELECT * FROM categories WHERE id=?', (category_id,)).fetchone()
            if not category or not category['active']:
                raise ArchiveError('category_not_found', 'الفئة غير موجودة أو موقوفة.', 422)
            latest = db.execute('SELECT COALESCE(MAX(sequence),0) FROM classifications WHERE document_id=?',
                                (document_id,)).fetchone()[0]
            if latest != expected_sequence:
                raise ArchiveError('stale_classification',
                                   'تغيّر تصنيف هذا المستند بعد فتحك له. أعد التحميل وراجع آخر حالة.', 409)
            previous = db.execute("SELECT * FROM classifications WHERE document_id=? AND kind='decision'"
                                  ' ORDER BY sequence DESC LIMIT 1', (document_id,)).fetchone()
            suggestion = db.execute("SELECT * FROM classifications WHERE document_id=? AND kind='suggestion'"
                                    ' ORDER BY sequence DESC LIMIT 1', (document_id,)).fetchone()
            if previous and previous['category_id'] == category_id:
                raise ArchiveError('unchanged', 'المستند معتمد بهذا التصنيف أصلًا.', 422)
            if previous and not reason:
                raise ArchiveError('reason_required', 'اذكر سبب إعادة التصنيف؛ التصنيف الحالي معتمد.', 422)
            agrees = bool(suggestion and suggestion['category_id'] == category_id)
            record = {'id': str(uuid.uuid4()), 'document_id': document_id, 'kind': 'decision',
                      'category_id': category_id, 'confidence': None, 'method': 'human',
                      'scores': None, 'evidence': None,
                      'basis': json.dumps({'previous_category_id': previous['category_id'] if previous else None,
                                           'suggestion_id': suggestion['id'] if suggestion else None,
                                           'suggested_category_id': suggestion['category_id'] if suggestion else None,
                                           'agrees_with_suggestion': agrees}),
                      'reason': reason, 'actor': actor, 'created_at': now()}
            db.execute(f"INSERT INTO classifications ({','.join(record)}) VALUES ({','.join('?' for _ in record)})",
                       list(record.values()))
            action = 'classification.changed' if previous else 'classification.confirmed'
            self.db._event(db, document_id, action,
                           {'category_id': category_id, 'previous_category_id': previous['category_id'] if previous else None,
                            'agrees_with_suggestion': agrees, 'reason': reason}, actor)
        return self.get(document_id)

    def has_decision(self, document_id: str) -> bool:
        with self.db.connect() as db:
            return db.execute("SELECT 1 FROM classifications WHERE document_id=? AND kind='decision'",
                              (document_id,)).fetchone() is not None

    # -- reads --------------------------------------------------------------------------------
    def get(self, document_id: str) -> dict:
        with self.db.connect() as db:
            current = db.execute('SELECT v.*, c.name AS category_name FROM document_categories v'
                                 ' LEFT JOIN categories c ON c.id=v.category_id WHERE v.document_id=?',
                                 (document_id,)).fetchone()
            history = db.execute('SELECT h.*, c.name AS category_name FROM classifications h'
                                 ' LEFT JOIN categories c ON c.id=h.category_id WHERE h.document_id=?'
                                 ' ORDER BY h.sequence DESC', (document_id,)).fetchall()
        history = [_row(row) for row in history]
        suggestion = next((item for item in history if item['kind'] == 'suggestion'), None)
        decision = next((item for item in history if item['kind'] == 'decision'), None)
        return {'document_id': document_id,
                'state': current['state'] if current else 'none',
                'category_id': current['category_id'] if current else None,
                'category_name': current['category_name'] if current else None,
                'sequence': history[0]['sequence'] if history else 0,
                'suggestion': suggestion, 'decision': decision, 'history': history}

    def queue(self, limit: int, offset: int) -> dict:
        where = "FROM document_categories v JOIN documents d ON d.id=v.document_id LEFT JOIN categories c" \
                " ON c.id=v.category_id WHERE v.state IN ('suggested','uncertain')"
        with self.db.connect() as db:
            total = db.execute('SELECT COUNT(*) ' + where).fetchone()[0]
            rows = db.execute('SELECT d.id AS document_id, d.filename, d.page_count, d.created_at, v.state,'
                              ' v.category_id, c.name AS category_name, v.confidence ' + where +
                              " ORDER BY v.state='uncertain', v.confidence DESC, d.created_at DESC LIMIT ? OFFSET ?",
                              (limit, offset)).fetchall()
        return {'items': [dict(row) for row in rows], 'total': total, 'limit': limit, 'offset': offset}

    def summary(self) -> dict:
        with self.db.connect() as db:
            rows = db.execute('SELECT state, COUNT(*) AS n FROM document_categories GROUP BY state').fetchall()
        counts = {'confirmed': 0, 'suggested': 0, 'uncertain': 0, 'none': 0}
        counts.update({row['state']: row['n'] for row in rows})
        return counts

    def documents_in(self, category_id: str) -> set[str]:
        with self.db.connect() as db:
            return {row[0] for row in db.execute('SELECT document_id FROM document_categories WHERE category_id=?',
                                                 (category_id,))}
