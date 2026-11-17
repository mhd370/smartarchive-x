"""Persisted OCR runs: queue, claim, process page by page, record provenance and review flags.

A run never edits the original or a previous run; each run is a new, versioned set of results.
"""
import json
import logging
import threading
import traceback
import uuid
from typing import Callable

from smartarchive.config import Settings
from smartarchive.domain.documents import ArchiveError
from smartarchive.persistence.database import Database, now
from smartarchive.persistence.storage import OriginalStore
from .ocr import Engine, TesseractEngine, Word, mean_confidence
from .layout import read_page
from . import paths as ocr_paths, regions
from .preprocess import prepare
from .quality import BOUNDS, assess
from .render import page_images

log = logging.getLogger(__name__)
SYSTEM = 'system:ocr'
FULL_RESOLUTION_DPI = BOUNDS['dpi'][1]


def _round(value):
    return None if value is None else round(value, 4)


class OcrService:
    def __init__(self, db: Database, store: OriginalStore, settings: Settings,
                 engine_factory: Callable[[], Engine] | None = None, texts=None):
        self.db, self.store, self.settings = db, store, settings
        self.texts = texts  # PageTexts: makes completed runs searchable in the same transaction
        self.on_ready: Callable[[str], None] | None = None  # called with the document id after a run completes
        self._factory = engine_factory
        self._engine: Engine | None = None
        self._engine_error: str | None = None
        self._extra_engines: dict[str, Engine] = {}

    # -- engine -------------------------------------------------------------------------------
    def engine(self) -> Engine | None:
        if self._engine is None and self._engine_error is None:
            try:
                if self._factory:
                    self._engine = self._factory()
                elif self.settings.tesseract:
                    self._engine = TesseractEngine(self.settings.tesseract, self.settings.ocr_languages,
                                                   self.settings.ocr_page_timeout_seconds,
                                                   self.settings.tessdata_dir)
                else:
                    self._engine_error = 'tesseract_not_found'
            except Exception as exc:  # recorded and reported, never hidden behind fake results
                self._engine_error = f'{type(exc).__name__}: {exc}'[:300]
        return self._engine

    def engine_for(self, languages: str | None) -> Engine:
        """The default engine, or one with other languages for an OCR path such as `model-ara` (paths.py)."""
        engine = self.engine()
        if not languages or not isinstance(engine, TesseractEngine):
            return engine
        if languages not in self._extra_engines:
            self._extra_engines[languages] = TesseractEngine(self.settings.tesseract, languages,
                                                             self.settings.ocr_page_timeout_seconds,
                                                             self.settings.tessdata_dir)
        return self._extra_engines[languages]

    def read(self, image) -> tuple[list, list]:
        """Lines of a prepared page and the steps that produced them (layout analysis, OCR path choice)."""
        settings = self.settings
        reader = read_page if settings.layout_analysis else (lambda engine, page: (engine.recognize(page), None))
        if len(settings.ocr_paths) > 1:
            lines, steps = ocr_paths.read(self.engine_for, image, settings.ocr_paths, settings.ocr_path_rule,
                                          settings.ocr_path_gate, reader)
            return lines, [step for step in (steps['layout'], steps['paths']) if step]
        lines, layout = reader(self.engine(), image)
        return lines, [layout] if layout else []

    @staticmethod
    def _regions(prepared, lines, read_steps, width: int, height: int) -> dict:
        """Heading, stamp and figure regions (regions.py) as normalized boxes on the original page."""
        tables = [t['box'] for step in read_steps if step.get('step') == 'layout' for t in step.get('tables') or []]
        try:
            found = regions.find(prepared.image, lines, tables)
        except Exception as exc:  # regions are evidence for people; they never fail an OCR run
            log.exception('Region detection failed')
            return {'step': 'regions', 'method': regions.METHOD, 'error': f'{type(exc).__name__}: {exc}'[:200]}
        out = []
        for region in found:
            item = {'kind': region['kind'], 'box': list(prepared.to_original(region['box'], width, height))}
            if region.get('text'):
                item['text'] = region['text'][:160]
            out.append(item)
        return {'step': 'regions', 'method': regions.METHOD, 'regions': out}

    def info(self) -> dict:
        engine = self.engine()
        if not engine:
            return {'configured': False, 'engine': None, 'version': None, 'languages': None,
                    'missing_languages': None, 'error': self._engine_error}
        return {'configured': True, 'engine': engine.name, 'version': engine.version(),
                'languages': getattr(engine, 'languages', None),
                'missing_languages': getattr(engine, 'missing', []), 'error': None,
                'layout': 'layout-v1' if self.settings.layout_analysis else 'none',
                'paths': {'method': ocr_paths.METHOD, 'paths': list(self.settings.ocr_paths),
                          'rule': self.settings.ocr_path_rule, 'gate': self.settings.ocr_path_gate}
                if len(self.settings.ocr_paths) > 1 else None}

    # -- queue ----------------------------------------------------------------------------------
    def enqueue(self, document: dict, actor: str, trigger: str) -> dict:
        engine = self.engine()
        if not engine:
            raise ArchiveError('ocr_unavailable', 'محرك OCR غير مثبت أو غير مهيأ على الخادم.', 503)
        run = {'id': str(uuid.uuid4()), 'document_id': document['id'], 'status': 'queued',
               'engine': engine.name, 'engine_version': engine.version(),
               'languages': getattr(engine, 'languages', self.settings.ocr_languages),
               'params': json.dumps({'dpi': self.settings.ocr_dpi, 'psm': 3, 'oem': 1, 'trigger': trigger,
                                     'quality_weights': self.settings.quality_weights,
                                     'review_threshold': self.settings.review_confidence_threshold,
                                     'ocr_paths': list(self.settings.ocr_paths), 'ocr_path_rule': self.settings.ocr_path_rule,
                                     'ocr_path_gate': self.settings.ocr_path_gate}),
               'created_by': actor, 'created_at': now(), 'pages_total': document['page_count'], 'pages_done': 0}
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM ocr_runs WHERE document_id=? AND status IN ('queued','processing')",
                          (document['id'],)).fetchone():
                raise ArchiveError('ocr_in_progress', 'توجد معالجة قيد الانتظار أو التنفيذ لهذا المستند.', 409)
            db.execute(f"INSERT INTO ocr_runs ({','.join(run)}) VALUES ({','.join('?' for _ in run)})", list(run.values()))
            self.db.set_status(db, document['id'], 'queued', 'OCR_QUEUED')
            self.db._event(db, document['id'], 'ocr.queued', {'run_id': run['id'], 'trigger': trigger}, actor)
        return self.run(run['id'])

    def recover(self):
        """Runs interrupted by a shutdown go back to the queue; their partial pages are discarded."""
        with self.db.connect() as db:
            for row in db.execute("SELECT id, document_id FROM ocr_runs WHERE status='processing'").fetchall():
                db.execute('DELETE FROM ocr_lines WHERE run_id=?', (row['id'],))
                db.execute('DELETE FROM page_analyses WHERE run_id=?', (row['id'],))
                db.execute("UPDATE ocr_runs SET status='queued', started_at=NULL, pages_done=0 WHERE id=?", (row['id'],))
                self.db.set_status(db, row['document_id'], 'queued', 'OCR_REQUEUED')
                self.db._event(db, row['document_id'], 'ocr.requeued', {'run_id': row['id']}, SYSTEM)

    def _claim(self) -> dict | None:
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM ocr_runs WHERE status='queued' ORDER BY created_at, id LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("UPDATE ocr_runs SET status='processing', started_at=? WHERE id=?", (now(), row['id']))
            self.db.set_status(db, row['document_id'], 'processing', 'OCR_RUNNING')
            self.db._event(db, row['document_id'], 'ocr.started', {'run_id': row['id']}, SYSTEM)
            return dict(row)

    def run_next(self) -> bool:
        run = self._claim()
        if not run:
            return False
        try:
            self._process(run)
        except Exception as exc:
            log.exception('OCR run %s failed', run['id'])
            message = f'{type(exc).__name__}: {exc}'[:500]
            with self.db.connect() as db:
                db.execute("UPDATE ocr_runs SET status='failed', finished_at=?, error=? WHERE id=?",
                           (now(), message, run['id']))
                self.db.set_status(db, run['document_id'], 'failed', 'OCR_FAILED')
                self.db._event(db, run['document_id'], 'ocr.failed', {'run_id': run['id'], 'error': message}, SYSTEM)
        return True

    # -- processing ---------------------------------------------------------------------------
    def _process(self, run: dict):
        record = self.db.get(run['document_id'])
        path = self.store.verified_path(record)
        engine = self.engine()
        if engine is None:
            raise RuntimeError(self._engine_error or 'OCR engine unavailable')
        threshold = self.settings.review_confidence_threshold
        page_results = []
        for page_no, image, dpi, dpi_source in page_images(path, record['mime_type'], self.settings.ocr_dpi):
            # A rendered PDF page has the resolution we chose, not a defect of the source: score it as full
            # resolution (as before rendering went from 300 to 200 dpi, which Tesseract reads better).
            quality = assess(image, max(dpi, FULL_RESOLUTION_DPI) if dpi_source == 'rendered' else dpi,
                             self.settings.quality_weights)
            width, height = image.size
            lines, steps = [], [{'step': 'skipped', 'reason': 'blank_page'}]
            if not quality.blank:
                prepared = prepare(image, quality, self.settings.tesseract)
                steps = prepared.steps
                recognized, read_steps = self.read(prepared.image)
                steps = steps + read_steps
                if self.settings.layout_analysis:
                    steps = steps + [self._regions(prepared, recognized, read_steps, width, height)]
                for line in recognized:
                    words = [{'text': w.text, 'confidence': w.confidence,
                              'box': prepared.to_original(w.box, width, height)} for w in line.words]
                    lines.append((line.text, line.confidence, prepared.to_original(line.box, width, height), words))
            all_words = [w for _, _, _, words in lines for w in words]
            confidence = mean_confidence([Word(w['text'], w['confidence'], (0, 0, 0, 0)) for w in all_words])
            text_length = sum(len(text) for text, *_ in lines)
            review = (not quality.blank) and (confidence is None or confidence < threshold or text_length == 0)
            page_results.append((confidence, text_length, review, quality.blank))
            analysis = {'run_id': run['id'], 'page_no': page_no, 'width': width, 'height': height,
                        'dpi': round(dpi, 1), 'dpi_source': dpi_source,
                        'metrics': json.dumps(quality.to_dict()), 'quality_score': quality.score,
                        'suggested_route': quality.route, 'blank': int(quality.blank),
                        'preprocessing': json.dumps(steps), 'mean_confidence': _round(confidence),
                        'review_required': int(review), 'text_length': text_length}
            with self.db.connect() as db:
                db.execute(f"INSERT INTO page_analyses ({','.join(analysis)}) VALUES ({','.join('?' for _ in analysis)})",
                           list(analysis.values()))
                db.executemany('INSERT INTO ocr_lines(run_id,page_no,line_no,text,confidence,x0,y0,x1,y1,words) '
                               'VALUES (?,?,?,?,?,?,?,?,?,?)',
                               [(run['id'], page_no, index + 1, text, _round(conf), *box, json.dumps(words, ensure_ascii=False))
                                for index, (text, conf, box, words) in enumerate(lines)])
                db.execute('UPDATE ocr_runs SET pages_done=? WHERE id=?', (page_no, run['id']))
        weighted = [(c, n) for c, n, _, blank in page_results if c is not None and n]
        total = sum(n for _, n in weighted)
        overall = round(sum(c * n for c, n in weighted) / total, 4) if total else None
        review = any(r for _, _, r, _ in page_results) or total == 0
        with self.db.connect() as db:
            db.execute("UPDATE ocr_runs SET status='ready', finished_at=?, mean_confidence=?, review_required=? WHERE id=?",
                       (now(), overall, int(review), run['id']))
            reason = 'REVIEW_REQUIRED' if review else 'OCR_COMPLETED'
            if self.texts:
                self.texts.index_run(db, run['id'], run['document_id'])
                flagged = any(r for _, _, r, _ in page_results)
                if flagged and self.texts.pending_count(db, run['document_id']) == 0:
                    reason = 'REVIEW_COMPLETED'  # every flagged page already has a human correction
            self.db.set_status(db, run['document_id'], 'ready', reason)
            self.db._event(db, run['document_id'], 'ocr.completed',
                           {'run_id': run['id'], 'mean_confidence': overall, 'review_required': review,
                            'pages': len(page_results), 'characters': total}, SYSTEM)
        if self.on_ready:
            self.on_ready(run['document_id'])

    # -- reads --------------------------------------------------------------------------------
    def run(self, run_id: str) -> dict:
        with self.db.connect() as db:
            row = db.execute('SELECT * FROM ocr_runs WHERE id=?', (run_id,)).fetchone()
            return self._public_run(dict(row)) if row else None

    @staticmethod
    def _public_run(row: dict) -> dict:
        row['params'] = json.loads(row['params'])
        row['review_required'] = None if row['review_required'] is None else bool(row['review_required'])
        return row

    def runs(self, document_id: str) -> list[dict]:
        with self.db.connect() as db:
            rows = db.execute('SELECT * FROM ocr_runs WHERE document_id=? ORDER BY created_at DESC, id', (document_id,))
            return [self._public_run(dict(row)) for row in rows.fetchall()]

    def pages(self, run_id: str) -> list[dict]:
        with self.db.connect() as db:
            rows = db.execute('SELECT * FROM page_analyses WHERE run_id=? ORDER BY page_no', (run_id,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['metrics'] = json.loads(item['metrics'])
            item['preprocessing'] = json.loads(item['preprocessing'])
            item['blank'], item['review_required'] = bool(item['blank']), bool(item['review_required'])
            result.append(item)
        return result

    def lines(self, run_id: str, page_no: int) -> list[dict]:
        with self.db.connect() as db:
            rows = db.execute('SELECT * FROM ocr_lines WHERE run_id=? AND page_no=? ORDER BY line_no',
                              (run_id, page_no)).fetchall()
        return [{'line_no': r['line_no'], 'text': r['text'], 'confidence': r['confidence'],
                 'box': [r['x0'], r['y0'], r['x1'], r['y1']], 'words': json.loads(r['words'])} for r in rows]

    def text(self, run_id: str, limit: int = 200_000) -> str:
        with self.db.connect() as db:
            rows = db.execute('SELECT page_no, text FROM ocr_lines WHERE run_id=? ORDER BY page_no, line_no', (run_id,))
            pages: dict[int, list[str]] = {}
            for row in rows:
                pages.setdefault(row['page_no'], []).append(row['text'])
        return '\n\n'.join('\n'.join(lines) for _, lines in sorted(pages.items()))[:limit]


class Worker:
    """Single background thread; SQLite is the queue, so nothing is lost on restart."""

    def __init__(self, service: OcrService, poll_seconds: float = 1.0):
        self.service, self.poll = service, poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self.service.recover()
        self._thread = threading.Thread(target=self._loop, name='smartarchive-ocr', daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                if not self.service.run_next():
                    self._stop.wait(self.poll)
            except Exception:
                log.error('OCR worker loop error:\n%s', traceback.format_exc())
                self._stop.wait(self.poll)

    def stop(self, timeout: float = 10.0):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
