"""Measure the system on the archive's own human-checked data.

OCR: every page a person corrected gives a reference (the latest revision) for the OCR text that was
corrected (the run the first revision was based on). CER and WER use the project's canonical normalization and
edit-operation rules (evaluation/metrics.py, policy normalized-v1: diacritics and tatweel ignored on both
sides), with an equivalent integer implementation that is fast enough for whole pages.
This is a *post-editing* rate: it counts what the reviewer changed, so it underestimates true error
when a reviewer leaves mistakes, and pages are not a random sample (low-confidence pages are reviewed
first). Report it as such.

Classification: every document a person classified gives a label (the latest decision). The prediction
is the suggestion that person saw (recorded in the first decision). Abstentions are counted separately
(coverage). Reviewers saw the suggestion, which can bias labels towards it.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import json

from smartarchive.evaluation.metrics import normalize
from smartarchive.persistence.database import Database

POLICY = 'normalized-v1'
MAX_PAGES = 300
MAX_CHARS = 8000
BUCKETS = [('low', 0.0, 0.6), ('medium', 0.6, 0.85), ('high', 0.85, 1.01)]


def fast_edits(reference, hypothesis) -> tuple[int, int, int]:
    """(substitutions, deletions, insertions): the same result and tie-breaking as metrics.levenshtein
    (substitution, then deletion, then insertion), with plain integer rows instead of objects."""
    m = len(hypothesis)
    dist, sub, dele, ins = list(range(m + 1)), [0] * (m + 1), [0] * (m + 1), list(range(m + 1))
    for i, left in enumerate(reference, 1):
        cd, cs, cdl, ci = [i], [0], [i], [0]
        for j in range(1, m + 1):
            if left == hypothesis[j - 1]:
                cd.append(dist[j - 1]); cs.append(sub[j - 1]); cdl.append(dele[j - 1]); ci.append(ins[j - 1])
                continue
            diagonal, above, before = dist[j - 1] + 1, dist[j] + 1, cd[j - 1] + 1
            if diagonal <= above and diagonal <= before:
                cd.append(diagonal); cs.append(sub[j - 1] + 1); cdl.append(dele[j - 1]); ci.append(ins[j - 1])
            elif above <= before:
                cd.append(above); cs.append(sub[j]); cdl.append(dele[j] + 1); ci.append(ins[j])
            else:
                cd.append(before); cs.append(cs[j - 1]); cdl.append(cdl[j - 1]); ci.append(ci[j - 1] + 1)
        dist, sub, dele, ins = cd, cs, cdl, ci
    return sub[m], dele[m], ins[m]


@lru_cache(maxsize=4096)
def _measure(reference: str, hypothesis: str) -> dict:
    """CER/WER under POLICY; cached because the same corrected pages are measured on every request."""
    ref, hyp = normalize(reference, POLICY), normalize(hypothesis, POLICY)
    result = {}
    for name, left, right in (('cer', ref, hyp), ('wer', ref.split(), hyp.split())):
        s, d, i = fast_edits(left, right)
        result[name] = {'substitutions': s, 'deletions': d, 'insertions': i, 'distance': s + d + i,
                        'reference_units': len(left), 'rate': (s + d + i) / len(left) if left else None}
    return result


def _rate(distance: int, units: int):
    return round(distance / units, 4) if units else None


def ocr_post_editing(db: Database) -> dict:
    with db.connect() as connection:
        pairs = connection.execute('''
            SELECT first.document_id, first.page_no, first.base_run_id, d.filename,
                   (SELECT text FROM page_revisions WHERE document_id=first.document_id AND page_no=first.page_no
                    ORDER BY version DESC LIMIT 1) AS reference,
                   (SELECT mean_confidence FROM page_analyses WHERE run_id=first.base_run_id AND page_no=first.page_no)
                    AS confidence
            FROM page_revisions first JOIN documents d ON d.id=first.document_id
            WHERE first.version=1 AND first.base_source='ocr' AND first.base_run_id IS NOT NULL
            ORDER BY first.created_at LIMIT ?''', (MAX_PAGES + 1,)).fetchall()
        pages, skipped = [], []
        for row in pairs[:MAX_PAGES]:
            hypothesis = '\n'.join(line[0] for line in connection.execute(
                'SELECT text FROM ocr_lines WHERE run_id=? AND page_no=? ORDER BY line_no',
                (row['base_run_id'], row['page_no'])))
            if len(row['reference']) > MAX_CHARS or len(hypothesis) > MAX_CHARS:
                skipped.append({'document_id': row['document_id'], 'page_no': row['page_no'], 'reason': 'too_long'})
                continue
            result = _measure(row['reference'], hypothesis)
            pages.append({'document_id': row['document_id'], 'filename': row['filename'], 'page_no': row['page_no'],
                          'run_id': row['base_run_id'], 'ocr_confidence': row['confidence'],
                          'cer': result['cer']['rate'], 'wer': result['wer']['rate'],
                          'char_errors': result['cer']['distance'], 'chars': result['cer']['reference_units'],
                          'word_errors': result['wer']['distance'], 'words': result['wer']['reference_units'],
                          'substitutions': result['cer']['substitutions'], 'deletions': result['cer']['deletions'],
                          'insertions': result['cer']['insertions']})
    defined = [p for p in pages if p['cer'] is not None]
    summary = {'pages': len(pages), 'chars': sum(p['chars'] for p in pages), 'words': sum(p['words'] for p in pages),
               'micro_cer': _rate(sum(p['char_errors'] for p in pages), sum(p['chars'] for p in pages)),
               'micro_wer': _rate(sum(p['word_errors'] for p in pages), sum(p['words'] for p in pages)),
               'macro_cer': round(sum(p['cer'] for p in defined) / len(defined), 4) if defined else None}
    buckets = []
    for name, low, high in BUCKETS:
        inside = [p for p in pages if p['ocr_confidence'] is not None and low <= p['ocr_confidence'] < high]
        buckets.append({'bucket': name, 'confidence_from': low, 'confidence_to': min(high, 1.0), 'pages': len(inside),
                        'micro_cer': _rate(sum(p['char_errors'] for p in inside), sum(p['chars'] for p in inside))})
    return {'policy': POLICY, 'summary': summary, 'by_confidence': buckets, 'pages': pages, 'skipped': skipped,
            'truncated': len(pairs) > MAX_PAGES,
            'note': 'Post-editing rate against human-corrected pages (not an independent ground truth).'}


def classification_accuracy(db: Database) -> dict:
    with db.connect() as connection:
        rows = connection.execute('''
            SELECT d.id AS document_id, d.filename,
              (SELECT category_id FROM classifications WHERE document_id=d.id AND kind='decision'
               ORDER BY sequence DESC LIMIT 1) AS label,
              (SELECT basis FROM classifications WHERE document_id=d.id AND kind='decision'
               ORDER BY sequence LIMIT 1) AS first_basis
            FROM documents d WHERE EXISTS (SELECT 1 FROM classifications c WHERE c.document_id=d.id AND kind='decision')
            ''').fetchall()
        names = {row['id']: row['name'] for row in connection.execute('SELECT id, name FROM categories')}
    items, skipped = [], 0
    for row in rows:
        basis = json.loads(row['first_basis'])
        if not basis.get('suggestion_id'):
            skipped += 1
            continue
        items.append({'document_id': row['document_id'], 'filename': row['filename'], 'label': row['label'],
                      'prediction': basis.get('suggested_category_id')})
    covered = [i for i in items if i['prediction']]
    correct = [i for i in covered if i['prediction'] == i['label']]
    confusion: dict[str, Counter] = defaultdict(Counter)
    for item in items:
        confusion[item['label']][item['prediction'] or 'abstain'] += 1
    per_category = []
    for category in sorted({i['label'] for i in items} | {i['prediction'] for i in covered}):
        tp = sum(1 for i in covered if i['prediction'] == category and i['label'] == category)
        fp = sum(1 for i in covered if i['prediction'] == category and i['label'] != category)
        fn = sum(1 for i in items if i['label'] == category and i['prediction'] != category)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if precision is not None and recall is not None else None)
        per_category.append({'category_id': category, 'name': names.get(category, category), 'support': tp + fn,
                             'predicted': tp + fp, 'precision': None if precision is None else round(precision, 4),
                             'recall': None if recall is None else round(recall, 4),
                             'f1': None if f1 is None else round(f1, 4)})
    defined_f1 = [c['f1'] for c in per_category if c['f1'] is not None and c['support']]
    return {'method': 'keywords-v1',
            'summary': {'labelled': len(items), 'skipped_without_suggestion': skipped, 'covered': len(covered),
                        'coverage': round(len(covered) / len(items), 4) if items else None,
                        'accuracy_when_suggested': round(len(correct) / len(covered), 4) if covered else None,
                        'accuracy_overall': round(len(correct) / len(items), 4) if items else None,
                        'macro_f1': round(sum(defined_f1) / len(defined_f1), 4) if defined_f1 else None},
            'per_category': per_category,
            'confusion': {label: dict(counts) for label, counts in confusion.items()},
            'names': names,
            'note': 'Labels are human decisions made after seeing the suggestion; accuracy may be optimistic.'}


def report(db: Database) -> dict:
    return {'generated_at': datetime.now(timezone.utc).isoformat(), 'ocr': ocr_post_editing(db),
            'classification': classification_accuracy(db)}
