"""Duplicate and version detection (`fingerprint-v1`).

- exact_duplicate: identical original bytes (same SHA-256).
- near_duplicate: almost the same text (MinHash estimate of word-3-gram Jaccard similarity >= 0.85), e.g.
  the same letter scanned twice or saved as PDF and as image.
- version_of: related text below the near-duplicate level that shares the same reference number (similarity
  >= 0.25, e.g. a letter re-issued under the same number with a new body) or the same subject (>= 0.45),
  e.g. an amended contract or a corrected decision. A reference number only links documents when it has at
  least four digits: OCR often truncates numbers (ع/٤٥٦/٢٠٢٤ read as «ع/4»), and those fragments are shared by
  unrelated documents (synthetic evaluation, Sprint 6: all 20 false version suggestions came from them).
  Only labelled or human-entered values link documents, never a subject guessed from a title.

Relations are suggestions until a reviewer confirms or rejects them. Nothing is merged or deleted.
"""
import hashlib
import json
import logging
import uuid

from smartarchive.domain.documents import ArchiveError
from smartarchive.persistence.database import Database, now
from smartarchive.search.arabic import normalize

log = logging.getLogger(__name__)
METHOD = 'fingerprint-v2'
PERMUTATIONS = 64
PRIME = (1 << 61) - 1
MIN_SHINGLES = 15
MIN_REFERENCE_DIGITS = 4
LINKING_CONFIDENCE = 0.8
NEAR, VERSION_SAME_REFERENCE, VERSION_SAME_SUBJECT = 0.85, 0.25, 0.45
_COEFFICIENTS = [(int.from_bytes(hashlib.sha256(f'a{i}'.encode()).digest()[:8], 'big') % PRIME | 1,
                  int.from_bytes(hashlib.sha256(f'b{i}'.encode()).digest()[:8], 'big') % PRIME)
                 for i in range(PERMUTATIONS)]


def shingles(text: str, size: int = 3) -> set[int]:
    words = normalize(text).split()
    return {int.from_bytes(hashlib.blake2b(' '.join(words[i:i + size]).encode(), digest_size=8).digest(), 'big')
            for i in range(max(0, len(words) - size + 1))}


def minhash(values: set[int]) -> list[int]:
    return [min((a * value + b) % PRIME for value in values) for a, b in _COEFFICIENTS]


def identifying(reference: str | None) -> bool:
    """A reference number specific enough to link two documents (at least four digits)."""
    return bool(reference) and sum(ch.isdigit() for ch in reference) >= MIN_REFERENCE_DIGITS


def similarity(left: list[int], right: list[int]) -> float:
    return sum(1 for x, y in zip(left, right) if x == y) / PERMUTATIONS


class Relations:
    def __init__(self, db: Database, metadata=None):
        self.db, self.metadata = db, metadata

    def fingerprint(self, document_id: str) -> dict:
        with self.db.connect() as db:
            document = db.execute('SELECT sha256 FROM documents WHERE id=?', (document_id,)).fetchone()
            if not document:
                raise ArchiveError('not_found', 'المستند غير موجود.', 404)
            text = '\n'.join(row[0] for row in db.execute(
                'SELECT text FROM page_texts WHERE document_id=? ORDER BY page_no', (document_id,)))
            values = shingles(text)
            signature = minhash(values) if len(values) >= MIN_SHINGLES else None
            row = (document_id, document['sha256'], json.dumps(signature) if signature else None, len(values),
                   hashlib.sha256(normalize(text).encode()).hexdigest(), now())
            db.execute('INSERT OR REPLACE INTO document_fingerprints(document_id,sha256,minhash,shingles,text_digest,'
                       'updated_at) VALUES (?,?,?,?,?,?)', row)
        return {'sha256': row[1], 'minhash': signature, 'shingles': len(values)}

    def detect(self, document_id: str) -> list[dict]:
        """Fingerprint the document and suggest relations to every other archived document."""
        mine = self.fingerprint(document_id)
        own_meta = self._linking_values(document_id)
        with self.db.connect() as db:
            others = db.execute('SELECT * FROM document_fingerprints WHERE document_id<>?', (document_id,)).fetchall()
        found = []
        for other in others:
            if other['sha256'] == mine['sha256']:
                found.append((other['document_id'], 'exact_duplicate', 1.0, {'sha256': mine['sha256']}))
                continue
            if not mine['minhash'] or not other['minhash']:
                continue
            score = similarity(mine['minhash'], json.loads(other['minhash']))
            if score >= NEAR:
                found.append((other['document_id'], 'near_duplicate', score, {'text_similarity': score}))
            elif score >= VERSION_SAME_REFERENCE and self.metadata:
                theirs = self._linking_values(other['document_id'])
                shared = [field for field in ('reference_number', 'subject')
                          if own_meta.get(field) and own_meta.get(field) == theirs.get(field)
                          and (field != 'reference_number' or identifying(own_meta[field]))]
                if ('reference_number' in shared) or ('subject' in shared and score >= VERSION_SAME_SUBJECT):
                    found.append((other['document_id'], 'version_of', score,
                                  {'text_similarity': score, 'shared_fields': shared}))
        created = []
        with self.db.connect() as db:
            for target, kind, score, evidence in found:
                pair = sorted([document_id, target])  # one relation per unordered pair and kind
                if db.execute('SELECT 1 FROM document_relations WHERE kind=? AND ((source_id=? AND target_id=?) OR'
                              ' (source_id=? AND target_id=?))', (kind, *pair, *reversed(pair))).fetchone():
                    continue
                relation = {'id': str(uuid.uuid4()), 'source_id': document_id, 'target_id': target, 'kind': kind,
                            'score': round(score, 4), 'method': METHOD, 'evidence': json.dumps(evidence, ensure_ascii=False),
                            'status': 'suggested', 'created_at': now()}
                db.execute(f"INSERT INTO document_relations ({','.join(relation)}) VALUES ({','.join('?' for _ in relation)})",
                           list(relation.values()))
                created.append(relation)
        return created

    def _linking_values(self, document_id: str) -> dict[str, str]:
        """Values trusted enough to link documents: entered by a person, or extracted from a labelled field
        (confidence >= 0.8). A subject guessed from a title («عقد توريد لمشروع ...») is shared by many documents."""
        if not self.metadata:
            return {}
        fields = self.metadata.get(document_id)['fields']
        return {name: item['normalized'] for name, item in fields.items() if item['normalized'] and
                (item['source'] == 'human' or (item['confidence'] or 0) >= LINKING_CONFIDENCE)}

    def detect_quietly(self, document_id: str):
        try:
            self.detect(document_id)
        except Exception:
            log.exception('Duplicate detection failed for %s', document_id)

    def ensure_fingerprinted(self) -> int:
        with self.db.connect() as db:
            ids = [row[0] for row in db.execute('SELECT id FROM documents d WHERE NOT EXISTS'
                                                ' (SELECT 1 FROM document_fingerprints f WHERE f.document_id=d.id)'
                                                ' ORDER BY created_at')]
        for document_id in ids:
            self.detect_quietly(document_id)
        return len(ids)

    def of(self, document_id: str) -> list[dict]:
        with self.db.connect() as db:
            rows = db.execute('''SELECT r.*, CASE WHEN r.source_id=? THEN r.target_id ELSE r.source_id END AS other_id
                FROM document_relations r WHERE r.source_id=? OR r.target_id=? ORDER BY r.score DESC''',
                              (document_id,) * 3).fetchall()
            names = {row['id']: dict(row) for row in db.execute('SELECT id, filename, created_at, page_count FROM documents')}
        result = []
        for row in rows:
            item = dict(row)
            item['evidence'] = json.loads(item['evidence'])
            other = names.get(item['other_id'], {})
            item.update(other_filename=other.get('filename'), other_created_at=other.get('created_at'),
                        direction='newer' if item['source_id'] == document_id else 'older')
            result.append(item)
        return result

    def review(self, relation_id: str, status: str, actor: str) -> dict:
        if status not in ('confirmed', 'rejected'):
            raise ArchiveError('invalid_status', 'الحالة يجب أن تكون تأكيدًا أو رفضًا.', 422)
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM document_relations WHERE id=?', (relation_id,)).fetchone()
            if not row:
                raise ArchiveError('relation_not_found', 'العلاقة غير موجودة.', 404)
            if row['status'] == status:
                raise ArchiveError('unchanged', 'العلاقة بهذه الحالة أصلًا.', 422)
            db.execute('UPDATE document_relations SET status=?, reviewed_by=?, reviewed_at=? WHERE id=?',
                       (status, actor, now(), relation_id))
            for doc in (row['source_id'], row['target_id']):
                self.db._event(db, doc, f'relation.{status}', {'relation_id': relation_id, 'kind': row['kind'],
                                                              'source_id': row['source_id'], 'target_id': row['target_id']}, actor)
        return dict(row) | {'status': status, 'reviewed_by': actor}

    def summary(self) -> dict:
        with self.db.connect() as db:
            rows = db.execute('SELECT kind, status, COUNT(*) AS n FROM document_relations GROUP BY kind, status').fetchall()
        out: dict[str, dict[str, int]] = {}
        for row in rows:
            out.setdefault(row['kind'], {})[row['status']] = row['n']
        return out
