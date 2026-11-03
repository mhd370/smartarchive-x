r"""Run the whole archive pipeline on a synthetic corpus and score it against the exact ground truth.

  .\.venv\Scripts\python.exe tools/evaluate_synthetic.py data\synthetic\corpus_v1 [--limit 40] [--work DIR]

The corpus (tools/synth_corpus.py) is imported into a separate, throw-away archive under
results/synthetic_eval/<name>/storage (never the real archive). Every file goes through the same steps as an
upload: validation and storage, folder filing, OCR (Tesseract, quality score, preprocessing), metadata
extraction, classification suggestion and duplicate/version detection. Then:

- OCR: CER/WER per page against the true text in reading order (policy normalized-v1), micro-averaged and split
  by scan quality level and layout. Reading order counts: a two-column page read across columns scores worse.
- Metadata: per field, the current value against the true value. Fields whose true value is not written in
  the document are reported separately (no extractor can find them).
- Classification: accuracy of the suggested type and of the first level (group), coverage (non-abstentions),
  precision on the answered documents, and a confusion table.
- Relations: precision/recall of suggested exact duplicates, near duplicates and versions (pairs, kind-aware).
- Search: Recall@10, MRR@10 and nDCG@10 over the generated queries (subjects and reference numbers), for the
  ranked (default) and the exact mode.

Interrupted runs resume with the same --work folder; --re-enrich re-scores new rules on the stored text. Results: report.json and report.md in the work folder.
All numbers are on synthetic data and must be reported as such.
"""
import argparse
from collections import Counter, defaultdict
import dataclasses
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
MIME = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.tif': 'image/tiff', '.tiff': 'image/tiff'}
FIELDS = ('reference_number', 'date', 'sender', 'recipient', 'subject', 'amount')
ACTOR = 'system:synthetic-eval'


# ------------------------------------------------------------------------------------------- scoring
def canonical(field: str, value) -> str:
    """Comparable form of a metadata value: unified letters and digits, no spacing differences."""
    from smartarchive.search.arabic import normalize
    if value is None:
        return ''
    text = str(value).translate(DIGITS)
    if field == 'amount':
        return re.sub(r'\D', '', text.split('.')[0])
    if field == 'reference_number':
        return re.sub(r'\s', '', normalize(text))
    return ' '.join(normalize(text).replace('-', ' ').split())


def score_metadata(truth: dict, predicted: dict, text: str) -> dict:
    """{field: {'expected', 'predicted', 'correct', 'in_text', 'cer'}} for the fields with a true value. `cer`
    is the character error of the comparable forms, capped at 1 (a missing value counts as 1)."""
    from smartarchive.operations.evaluation import fast_edits
    plain = canonical('subject', text)
    digits = re.sub(r'\D', '', text.translate(DIGITS))
    out = {}
    for field in FIELDS:
        expected = truth.get(field)
        if not expected:
            continue
        want, got = canonical(field, expected), canonical(field, predicted.get(field))
        if field == 'date':
            in_text = True  # always printed on the page, in one of three formats
        elif field == 'amount':
            in_text = want in digits
        elif field == 'reference_number':
            in_text = want in re.sub(r'\s', '', plain)
        else:
            in_text = want in plain
        edits = sum(fast_edits(want, got)) if want else 0
        out[field] = {'expected': expected, 'predicted': predicted.get(field), 'correct': bool(got) and got == want,
                      'in_text': in_text, 'cer': round(min(1.0, edits / len(want)), 4) if want else None}
    return out


def true_pairs(manifest: list[dict]) -> dict[frozenset, str]:
    return {frozenset((entry['doc_id'], relation['target'])): relation['kind']
            for entry in manifest for relation in entry['relations']}


def score_relations(truth: dict[frozenset, str], predicted: list[tuple[str, str, str]]) -> dict:
    """Kind-aware precision/recall, plus pair detection regardless of kind."""
    found = {}
    for left, right, kind in predicted:
        found.setdefault(frozenset((left, right)), set()).add(kind)
    result = {}
    for kind in ('exact_duplicate', 'near_duplicate', 'version_of'):
        want = {pair for pair, k in truth.items() if k == kind}
        got = {pair for pair, kinds in found.items() if kind in kinds}
        hit = len(want & got)
        result[kind] = {'true': len(want), 'suggested': len(got), 'correct': hit,
                        'precision': hit / len(got) if got else None, 'recall': hit / len(want) if want else None}
    pairs_hit = len(set(truth) & set(found))
    result['any_relation'] = {'true': len(truth), 'suggested': len(found), 'correct': pairs_hit,
                              'precision': pairs_hit / len(found) if found else None,
                              'recall': pairs_hit / len(truth) if truth else None}
    return result


def retrieval(ranked: list[str], relevant: set[str], k: int = 10) -> dict:
    top = ranked[:k]
    hits = [1 if doc in relevant else 0 for doc in top]
    dcg = sum(hit / math.log2(rank + 2) for rank, hit in enumerate(hits))
    ideal = sum(1 / math.log2(rank + 2) for rank in range(min(k, len(relevant))))
    first = next((rank for rank, hit in enumerate(hits, 1) if hit), None)
    return {'recall': sum(hits) / len(relevant) if relevant else 0.0, 'mrr': 1 / first if first else 0.0,
            'ndcg': dcg / ideal if ideal else 0.0}


def rate(items: list[dict], key: str) -> float | None:
    distance = sum(item[key]['distance'] for item in items)
    units = sum(item[key]['reference_units'] for item in items)
    return round(distance / units, 4) if units else None


def mean(values) -> float | None:
    values = list(values)
    return round(sum(values) / len(values), 4) if values else None


# ------------------------------------------------------------------------------------------- pipeline
class Pipeline:
    def __init__(self, work: Path, engine_factory=None, languages: str | None = None, tessdata: Path | None = None,
                 dpi: int | None = None):
        from smartarchive.classification.service import Classifications
        from smartarchive.config import Settings
        from smartarchive.enrichment.duplicates import Relations
        from smartarchive.enrichment.metadata import Metadata
        from smartarchive.persistence.database import Database
        from smartarchive.persistence.storage import OriginalStore
        from smartarchive.processing.pipeline import OcrService
        from smartarchive.search.pages import PageTexts
        from smartarchive.services.documents import Documents
        from smartarchive.services.folders import Folders
        settings = dataclasses.replace(Settings.from_env(), storage_dir=(work / 'storage').resolve(),
                                       backup_dir=(work / 'backups').resolve())
        if languages:
            settings = dataclasses.replace(settings, ocr_languages=languages)
        if tessdata:
            settings = dataclasses.replace(settings, tessdata_dir=tessdata.resolve())
        if dpi:
            settings = dataclasses.replace(settings, ocr_dpi=dpi)
        self.db = Database(settings.storage_dir / 'archive.sqlite3')
        self.store = OriginalStore(settings)
        self.store.initialize()
        self.db.initialize()
        self.documents, self.folders, self.texts = Documents(self.db, self.store), Folders(self.db), PageTexts(self.db)
        self.metadata = Metadata(self.db)
        self.relations = Relations(self.db, self.metadata)
        self.classes = Classifications(self.db, models_dir=settings.storage_dir / 'models')
        self.classes.seed()
        self.ocr = OcrService(self.db, self.store, settings, engine_factory, self.texts)
        self.ocr.on_ready = self.enrich

    def enrich(self, document_id: str):  # the same steps, in the same order, as the API's after_text_change hook
        self.metadata.run_quietly(document_id)
        self.classes.suggest_quietly(document_id, trigger='auto')
        self.relations.detect_quietly(document_id)

    def ingest(self, path: Path, folder: str) -> str:
        with path.open('rb') as stream:
            record = self.documents.ingest(stream, path.name, MIME[path.suffix.lower()], ACTOR, 'OCR_NOT_REQUESTED')
        self.folders.file(record['id'], self.folders.ensure_path(folder, ACTOR)['id'], ACTOR)
        self.relations.detect_quietly(record['id'])  # exact duplicates are known before any OCR
        self.ocr.enqueue(self.documents.get(record['id']), ACTOR, 'import')
        return record['id']

    def page_texts(self, document_id: str) -> dict[int, str]:
        with self.db.connect() as db:
            return {row['page_no']: row['text'] for row in db.execute(
                'SELECT page_no, text FROM page_texts WHERE document_id=? ORDER BY page_no', (document_id,))}

    def predicted_relations(self) -> list[tuple[str, str, str]]:
        with self.db.connect() as db:
            return [(row['source_id'], row['target_id'], row['kind'])
                    for row in db.execute('SELECT source_id, target_id, kind FROM document_relations')]


def evaluate(corpus: Path, work: Path, limit: int | None = None, engine_factory=None, log=print,
             languages: str | None = None, tessdata: Path | None = None, re_enrich: bool = False,
             dpi: int | None = None, classifier_model: Path | None = None) -> dict:
    from smartarchive.operations.evaluation import _measure
    manifest = json.loads((corpus / 'manifest.json').read_text(encoding='utf-8'))
    entries = manifest['documents'][:limit] if limit else manifest['documents']
    keep = {entry['doc_id'] for entry in entries}
    for entry in entries:  # a relation to a document outside --limit cannot be found; drop it from the truth
        entry['relations'] = [r for r in entry['relations'] if r['target'] in keep]
    work.mkdir(parents=True, exist_ok=True)
    pipeline = Pipeline(work, engine_factory, languages, tessdata, dpi)
    if not pipeline.ocr.engine():
        raise SystemExit(f'OCR engine unavailable: {pipeline.ocr._engine_error}')
    if pipeline.ocr.info().get('missing_languages'):
        raise SystemExit(f"OCR languages not installed: {pipeline.ocr.info()['missing_languages']}")
    if classifier_model:  # a model trained elsewhere (e.g. on corpus_v1) classifies this corpus
        import shutil
        target = work / 'storage' / 'models'
        target.mkdir(parents=True, exist_ok=True)
        for name in ('classifier.joblib', 'classifier.json'):
            shutil.copy2(classifier_model / name, target / name)
    state_path = work / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'ids': {}}
    started = time.time()
    for entry in entries:
        if entry['doc_id'] not in state['ids']:
            state['ids'][entry['doc_id']] = pipeline.ingest(corpus / entry['file'], 'مجموعة اصطناعية/' + entry['folder'])
            state_path.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    pipeline.ocr.recover()
    done = 0
    while pipeline.ocr.run_next():
        done += 1
        if done % 10 == 0:
            log(f'  OCR {done} documents, {time.time() - started:.0f}s')
    log(f'OCR finished ({done} documents this session, {time.time() - started:.0f}s). Scoring...')
    ids = state['ids']
    back = {value: key for key, value in ids.items()}
    if re_enrich:  # new extraction rules or classifier on the stored OCR text, without running OCR again
        with pipeline.db.connect() as db:  # throw-away archive: relations are recomputed under the new rules
            db.execute('DELETE FROM document_relations')
        for entry in entries:
            pipeline.relations.detect_quietly(ids[entry['doc_id']])  # exact duplicates of pages without text
        for entry in entries:
            pipeline.enrich(ids[entry['doc_id']])
        log(f'Re-enriched {len(entries)} documents.')

    pages, metadata_rows, classified, per_doc = [], [], [], []
    for number, entry in enumerate(entries, 1):
        truth = json.loads((corpus / 'ground_truth' / f"{entry['doc_id']}.json").read_text(encoding='utf-8'))
        document_id = ids[entry['doc_id']]
        texts = pipeline.page_texts(document_id)
        doc_pages = []
        for page in truth['pages']:
            measured = _measure(page['text'], texts.get(page['page_no'], ''))
            doc_pages.append({'doc_id': entry['doc_id'], 'page_no': page['page_no'], 'quality': entry['quality'],
                              'layout': entry['layout'], 'type': entry['type'], **measured})
        pages += doc_pages
        whole = '\n'.join(page['text'] for page in truth['pages'])
        fields = score_metadata(truth['metadata'], pipeline.metadata.values(document_id), whole)
        for field, row in fields.items():
            metadata_rows.append({'doc_id': entry['doc_id'], 'type': entry['type'], 'quality': entry['quality'],
                                  'field': field, **row})
        record = pipeline.classes.get(document_id)
        suggestion = record.get('suggestion') or {}
        basis = suggestion.get('basis') or {}
        classified.append({'doc_id': entry['doc_id'], 'type': entry['type'], 'group': entry['group'],
                           'quality': entry['quality'], 'predicted': suggestion.get('category_id'),
                           'predicted_group': basis.get('group_id'), 'confidence': suggestion.get('confidence'),
                           'reason': suggestion.get('reason')})
        per_doc.append({'doc_id': entry['doc_id'], 'file': entry['file'], 'type': entry['type'],
                        'quality': entry['quality'], 'layout': entry['layout'],
                        'cer': rate(doc_pages, 'cer'), 'predicted_type': suggestion.get('category_id'),
                        'metadata_correct': sum(1 for row in fields.values() if row['correct']),
                        'metadata_fields': len(fields)})
        if number % 25 == 0:
            log(f'  scored {number}/{len(entries)}')

    def ocr_block(items):
        return {'pages': len(items), 'cer': rate(items, 'cer'), 'wer': rate(items, 'wer'),
                'median_page_cer': sorted(i['cer']['rate'] or 0 for i in items)[len(items) // 2] if items else None}

    ocr = {'all': ocr_block(pages)}
    for key in ('quality', 'layout', 'type'):
        groups = defaultdict(list)
        for item in pages:
            groups[item[key]].append(item)
        ocr[f'by_{key}'] = {name: ocr_block(items) for name, items in sorted(groups.items())}

    def meta_block(rows):
        return {'fields': len(rows), 'accuracy': mean(1.0 if r['correct'] else 0.0 for r in rows),
                'mean_value_cer': mean(r['cer'] for r in rows)}

    from smartarchive.enrichment.metadata import METHOD as metadata_method
    metadata = {'method': metadata_method, 'all': meta_block(metadata_rows),
                'written_in_document': meta_block([r for r in metadata_rows if r['in_text']]),
                'not_written_in_document': meta_block([r for r in metadata_rows if not r['in_text']]),
                'by_field': {}, 'by_quality': {}}
    for field in FIELDS:
        rows = [r for r in metadata_rows if r['field'] == field]
        if rows:
            metadata['by_field'][field] = {**meta_block([r for r in rows if r['in_text']]),
                                           'not_written_in_document': sum(1 for r in rows if not r['in_text'])}
    for level in sorted({r['quality'] for r in metadata_rows}):
        metadata['by_quality'][level] = meta_block([r for r in metadata_rows if r['quality'] == level and r['in_text']])
    metadata['errors_sample'] = [r for r in metadata_rows if r['in_text'] and not r['correct']][:40]

    answered = [c for c in classified if c['predicted']]
    confusion = Counter((c['type'], c['predicted'] or '(abstained)') for c in classified)
    classification = {
        'method': pipeline.classes.model_info()['active_method'], 'documents': len(classified), 'coverage': mean(1.0 if c['predicted'] else 0.0 for c in classified),
        'accuracy': mean(1.0 if c['predicted'] == c['type'] else 0.0 for c in classified),
        'precision_when_answered': mean(1.0 if c['predicted'] == c['type'] else 0.0 for c in answered),
        'group_accuracy': mean(1.0 if c['predicted_group'] == c['group'] else 0.0 for c in classified),
        'by_quality': {level: {'documents': len(items), 'accuracy': mean(1.0 if c['predicted'] == c['type'] else 0.0
                                                                          for c in items)}
                       for level in sorted({c['quality'] for c in classified})
                       for items in [[c for c in classified if c['quality'] == level]]},
        'confusion': [{'true': t, 'predicted': p, 'count': n} for (t, p), n in sorted(confusion.items())]}

    predicted = [(back[s], back[t], kind) for s, t, kind in pipeline.predicted_relations() if s in back and t in back]
    from smartarchive.enrichment.duplicates import METHOD as relations_method
    relations = {'method': relations_method, **score_relations(true_pairs(entries), predicted)}

    queries = [q for q in json.loads((corpus / 'queries.json').read_text(encoding='utf-8'))
               if set(q['relevant']) <= keep]
    from smartarchive.search.ranked import METHOD as ranked_method
    search = {'queries': len(queries)}
    for mode, run, method in (('ranked', pipeline.texts.search_ranked, ranked_method),
                              ('exact', pipeline.texts.search, 'substring-v1 (all terms, normalized)')):
        scored = []
        for query in queries:
            result = run(query['query'], 10, 0)
            ranking = [back.get(item['document']['id']) for item in result['items']]
            scored.append({'id': query['id'], 'kind': query['kind'], **retrieval(ranking, set(query['relevant']))})
        block = {'method': method}
        for kind in ('all', 'subject', 'reference_number'):
            items = [s for s in scored if kind == 'all' or s['kind'] == kind]
            block[kind] = {'queries': len(items), 'recall@10': mean(s['recall'] for s in items),
                           'mrr@10': mean(s['mrr'] for s in items), 'ndcg@10': mean(s['ndcg'] for s in items)}
        search[mode] = block

    report = {'corpus': str(corpus), 'generator': manifest.get('generator'), 'seed': manifest.get('seed'),
              'synthetic': True, 'documents': len(entries), 'pages': len(pages),
              'finished_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'ocr_engine': {k: pipeline.ocr.info().get(k) for k in ('engine', 'version', 'languages')},
              'tessdata_dir': str(pipeline.ocr.settings.tessdata_dir or ''), 'pdf_render_dpi': pipeline.ocr.settings.ocr_dpi,
              'ocr': ocr, 'metadata': metadata,
              'classification': classification, 'relations': relations, 'search': search, 'documents_detail': per_doc}
    (work / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    (work / 'report.md').write_text(markdown(report), encoding='utf-8')
    return report


def pct(value) -> str:
    return '—' if value is None else f'{value * 100:.1f}%'


def markdown(report: dict) -> str:
    ocr, meta, cls, rel, search = (report[k] for k in ('ocr', 'metadata', 'classification', 'relations', 'search'))
    engine = report.get('ocr_engine') or {}
    lines = [f"# Synthetic evaluation ({report['generator']}, seed {report['seed']})", '',
             f"{report['documents']} documents, {report['pages']} pages. **Synthetic data**: report as such. "
             f"OCR: {engine.get('engine')} {engine.get('version')}, languages `{engine.get('languages')}`, "
             f"PDF pages rendered at {report.get('pdf_render_dpi')} dpi.", '',
             '## OCR (CER / WER, normalized-v1)', '', '| Split | Pages | CER | WER |', '|---|---|---|---|',
             f"| all | {ocr['all']['pages']} | {pct(ocr['all']['cer'])} | {pct(ocr['all']['wer'])} |"]
    for key in ('by_quality', 'by_layout'):
        for name, block in ocr[key].items():
            lines.append(f"| {key[3:]}: {name} | {block['pages']} | {pct(block['cer'])} | {pct(block['wer'])} |")
    lines += ['', f"## Metadata ({meta.get('method', 'rules')})", '',
              f"Accuracy on values written in the document: {pct(meta['written_in_document']['accuracy'])} "
              f"({meta['written_in_document']['fields']} fields).", '', '| Field | Fields | Exact | Mean value CER | Not in document |',
              '|---|---|---|---|---|']
    for field, block in meta['by_field'].items():
        lines.append(f"| {field} | {block['fields']} | {pct(block['accuracy'])} | {pct(block['mean_value_cer'])} | "
                     f"{block['not_written_in_document']} |")
    lines += ['', f"## Classification ({cls.get('method', 'keywords')})", '',
              f"Accuracy {pct(cls['accuracy'])}, coverage {pct(cls['coverage'])}, precision when answered "
              f"{pct(cls['precision_when_answered'])}, first level (group) {pct(cls['group_accuracy'])}.", '',
              f"## Duplicates and versions ({rel.get('method', 'fingerprint')})", '', '| Kind | True | Suggested | Precision | Recall |',
              '|---|---|---|---|---|']
    for kind, block in rel.items():
        if kind == 'method':
            continue
        lines.append(f"| {kind} | {block['true']} | {block['suggested']} | {pct(block['precision'])} | {pct(block['recall'])} |")
    lines += ['', '## Search', '', '| Mode | Queries | n | Recall@10 | MRR@10 | nDCG@10 |', '|---|---|---|---|---|---|']
    for mode in ('ranked', 'exact'):
        for kind in ('all', 'subject', 'reference_number'):
            block = search[mode][kind]
            lines.append(f"| {mode} ({search[mode]['method']}) | {kind} | {block['queries']} | {pct(block['recall@10'])} | "
                         f"{pct(block['mrr@10'])} | {pct(block['ndcg@10'])} |")
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--work', type=Path, help='work folder (default results/synthetic_eval/<corpus name>)')
    parser.add_argument('--limit', type=int, help='only the first N documents of the manifest')
    parser.add_argument('--languages', help='Tesseract languages, e.g. ara+eng or script/Arabic+ara')
    parser.add_argument('--tessdata', type=Path, help='models folder (see tools/fetch_ocr_models.py)')
    parser.add_argument('--dpi', type=int, help='PDF rendering resolution for OCR (default: SMARTARCHIVE_OCR_DPI or 200)')
    parser.add_argument('--classifier-model', type=Path,
                        help='model folder from tools/train_classifier.py (default: keyword baseline)')
    parser.add_argument('--re-enrich', action='store_true',
                        help='re-run metadata, classification and relations on the stored text (no new OCR)')
    args = parser.parse_args(argv)
    corpus = args.corpus.resolve()
    if not (corpus / 'manifest.json').is_file():
        parser.error(f'not a synthetic corpus (no manifest.json): {corpus}')
    suffix = (f'_first{args.limit}' if args.limit else '') + \
        (('_' + args.languages.replace('/', '-').replace('+', '_')) if args.languages else '') + \
        (f'_{args.dpi}dpi' if args.dpi else '')
    work = (args.work or ROOT / 'results' / 'synthetic_eval' / (corpus.name + suffix)).resolve()
    model = args.classifier_model.resolve() if args.classifier_model else None
    report = evaluate(corpus, work, args.limit, languages=args.languages, tessdata=args.tessdata,
                      re_enrich=args.re_enrich, dpi=args.dpi, classifier_model=model,
                      log=lambda *items: print(*items, flush=True))  # progress in logs
    print(markdown(report))
    print(f'Report: {work / "report.json"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
