"""Archive folders: a tree whose paths are stable evidence (folder of a document) for classification and search.

Paths are '/'-joined folder names. Names are trimmed and may not contain '/' or control characters.
Folders are never deleted; a document is filed in at most one folder and every move is audited.
"""
import re
import uuid

from smartarchive.domain.documents import ArchiveError
from smartarchive.persistence.database import Database, now

INVALID = re.compile(r'[/\\\x00-\x1f\x7f]')


def clean_name(name: str) -> str:
    name = ' '.join((name or '').split())
    if not 1 <= len(name) <= 120 or INVALID.search(name) or name in ('.', '..'):
        raise ArchiveError('invalid_folder_name', 'اسم المجلد غير صالح (1–120 حرفًا، دون / أو \\).', 422)
    return name


class Folders:
    def __init__(self, db: Database):
        self.db = db

    def tree(self) -> list[dict]:
        """All folders with direct and recursive document counts, ordered by path."""
        with self.db.connect() as db:
            rows = [dict(row) for row in db.execute(
                'SELECT f.*, (SELECT COUNT(*) FROM document_folders d WHERE d.folder_id=f.id) AS documents'
                ' FROM folders f ORDER BY f.path')]
        for row in rows:
            prefix = row['path'] + '/'
            row['total_documents'] = row['documents'] + sum(other['documents'] for other in rows
                                                            if other['path'].startswith(prefix))
            row['depth'] = row['path'].count('/')
        return rows

    def get(self, folder_id: str) -> dict:
        with self.db.connect() as db:
            row = db.execute('SELECT * FROM folders WHERE id=?', (folder_id,)).fetchone()
        if not row:
            raise ArchiveError('folder_not_found', 'المجلد غير موجود.', 404)
        return dict(row)

    def create(self, name: str, parent_id: str | None, actor: str) -> dict:
        name = clean_name(name)
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return self._create(db, name, parent_id, actor)

    @staticmethod
    def _create(db, name: str, parent_id: str | None, actor: str) -> dict:
        parent = None
        if parent_id:
            parent = db.execute('SELECT * FROM folders WHERE id=?', (parent_id,)).fetchone()
            if not parent:
                raise ArchiveError('folder_not_found', 'المجلد الأب غير موجود.', 404)
        path = f"{parent['path']}/{name}" if parent else name
        if db.execute('SELECT 1 FROM folders WHERE path=?', (path,)).fetchone():
            raise ArchiveError('duplicate_folder', 'يوجد مجلد بهذا الاسم في المكان نفسه.', 409)
        row = {'id': str(uuid.uuid4()), 'parent_id': parent_id, 'name': name, 'path': path,
               'created_by': actor, 'created_at': now()}
        db.execute('INSERT INTO folders(id,parent_id,name,path,created_by,created_at) VALUES (?,?,?,?,?,?)',
                   tuple(row.values()))
        return row

    def ensure_path(self, path: str, actor: str) -> dict:
        """Create every missing folder along a '/'-separated path and return the last one (used by import)."""
        names = [clean_name(part) for part in path.replace('\\', '/').split('/') if part.strip()]
        if not names:
            raise ArchiveError('invalid_folder_name', 'مسار المجلد فارغ.', 422)
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            parent = None
            for index in range(len(names)):
                current = '/'.join(names[:index + 1])
                row = db.execute('SELECT * FROM folders WHERE path=?', (current,)).fetchone()
                parent = dict(row) if row else self._create(db, names[index], parent['id'] if parent else None, actor)
            return parent

    def file(self, document_id: str, folder_id: str | None, actor: str) -> dict | None:
        """Put a document in a folder (or take it out with None); audited as document.filed."""
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM documents WHERE id=?', (document_id,)).fetchone():
                raise ArchiveError('not_found', 'المستند غير موجود.', 404)
            previous = db.execute('SELECT f.id, f.path FROM document_folders d JOIN folders f ON f.id=d.folder_id'
                                  ' WHERE d.document_id=?', (document_id,)).fetchone()
            target = None
            if folder_id:
                target = db.execute('SELECT * FROM folders WHERE id=?', (folder_id,)).fetchone()
                if not target:
                    raise ArchiveError('folder_not_found', 'المجلد غير موجود.', 404)
            if (previous['id'] if previous else None) == folder_id:
                return dict(target) if target else None
            if folder_id:
                db.execute('INSERT OR REPLACE INTO document_folders(document_id,folder_id,assigned_by,assigned_at)'
                           ' VALUES (?,?,?,?)', (document_id, folder_id, actor, now()))
            else:
                db.execute('DELETE FROM document_folders WHERE document_id=?', (document_id,))
            self.db._event(db, document_id, 'document.filed',
                           {'from': previous['path'] if previous else None, 'to': target['path'] if target else None},
                           actor)
            return dict(target) if target else None

    def of(self, document_id: str) -> dict | None:
        with self.db.connect() as db:
            row = db.execute('SELECT f.* FROM document_folders d JOIN folders f ON f.id=d.folder_id'
                             ' WHERE d.document_id=?', (document_id,)).fetchone()
        return dict(row) if row else None


SUGGEST_METHOD = 'folder-knn-v1'
SUGGEST_NEIGHBOURS = 5


def suggest_folders(db_handle, document_id: str, k: int = SUGGEST_NEIGHBOURS) -> dict:
    """Folders where the k filed documents most similar to this one (TF-IDF cosine over their text) are kept.

    Folder placement is archival evidence: a document usually belongs where similar documents already are. Each
    folder scores the summed similarity of its neighbours; the neighbours are returned as the evidence. It only
    suggests: filing stays a person's action. Measured by tools/classification_experiments.py (ADR 0015).
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from smartarchive.search.arabic import normalize
    with db_handle.connect() as db:
        if not db.execute('SELECT 1 FROM documents WHERE id=?', (document_id,)).fetchone():
            raise ArchiveError('not_found', 'المستند غير موجود.', 404)
        texts: dict[str, list[str]] = {}
        for row in db.execute('SELECT document_id, text FROM page_texts ORDER BY document_id, page_no'):
            texts.setdefault(row[0], []).append(row[1])
        placed = {row[0]: (row[1], row[2]) for row in db.execute(
            'SELECT d.document_id, f.id, f.path FROM document_folders d JOIN folders f ON f.id=d.folder_id')}
        names = {row[0]: row[1] for row in db.execute('SELECT id, filename FROM documents')}
    own = normalize(' '.join(texts.get(document_id, [])))
    result = {'method': SUGGEST_METHOD, 'document_id': document_id, 'current_folder_id': placed.get(document_id, (None,))[0],
              'items': []}
    others = [d for d in placed if d != document_id and normalize(' '.join(texts.get(d, []))).strip()]
    if not own.strip() or not others:
        result['reason'] = 'no_text' if not own.strip() else 'no_filed_documents'
        return result
    corpus = [own] + [normalize(' '.join(texts[d])) for d in others]
    try:
        matrix = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True).fit_transform(corpus)
    except ValueError:  # nothing but stop-words or empty vocabulary
        result['reason'] = 'no_text'
        return result
    similarity = (matrix[1:] @ matrix[0].T).toarray().ravel()
    best = sorted(range(len(others)), key=lambda i: -similarity[i])[:k]
    votes: dict[str, dict] = {}
    for i in best:
        if similarity[i] <= 0:
            continue
        folder_id, path = placed[others[i]]
        entry = votes.setdefault(folder_id, {'folder_id': folder_id, 'path': path, 'score': 0.0, 'evidence': []})
        entry['score'] += float(similarity[i])
        entry['evidence'].append({'document_id': others[i], 'filename': names.get(others[i]),
                                  'similarity': round(float(similarity[i]), 3)})
    total = sum(v['score'] for v in votes.values()) or 1.0
    result['items'] = [{**v, 'score': round(v['score'] / total, 3)}
                       for v in sorted(votes.values(), key=lambda v: -v['score'])[:3]]
    if not result['items']:
        result['reason'] = 'no_similar_documents'
    return result
