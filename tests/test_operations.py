"""Backup, verification, restore, integrity reconciliation and archive evaluation (Sprint 4)."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from smartarchive.classification.service import Classifications
from smartarchive.domain.documents import ArchiveError
from smartarchive.operations.backup import Backups, integrity, restore, verify_file
from smartarchive.operations.evaluation import classification_accuracy, ocr_post_editing
from smartarchive.persistence.database import Database
from smartarchive.search.pages import PageTexts


class Archive(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.storage = self.root / 'storage'
        self.db = Database(self.storage / 'archive.sqlite3')
        self.db.initialize()

    def document(self, content: bytes = b'\x89PNG fake original', name='قرار.png', text=None) -> str:
        doc_id = str(uuid.uuid4())
        key = f'{doc_id}/original.png'
        path = self.storage / 'originals' / key
        path.parent.mkdir(parents=True)
        path.write_bytes(content)
        with self.db.connect() as db:
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (doc_id, name, len(content), 'image/png', hashlib.sha256(content).hexdigest(), key, 1,
                        'ready', 'OCR_COMPLETED', '2026-01-01T00:00:00', '2026-01-01T00:00:00'))
            self.db._event(db, doc_id, 'document.uploaded', {}, 'admin')
        return doc_id


class BackupTests(Archive):
    def test_backup_verifies_and_restores_into_an_empty_directory_only(self):
        first, second = self.document(b'one'), self.document(b'two' * 1000, 'b.png')
        backups = Backups(self.storage, app_version='test')
        created = backups.create('admin')
        self.assertEqual((created['document_count'], created['created_by']), (2, 'admin'))
        self.assertEqual([item['name'] for item in backups.list()], [created['name']])
        report = backups.verify(created['name'], 'admin')
        self.assertTrue(report['ok'], report['problems'])

        target = self.root / 'restored'
        result = restore(backups.path(created['name']), target)
        self.assertEqual(result['documents'], 2)
        restored = Database(target / 'archive.sqlite3')
        self.assertEqual({row['id'] for row in restored.list('', None, None, 10, 0)['items']}, {first, second})
        self.assertEqual((target / 'originals' / f'{second}/original.png').read_bytes(), b'two' * 1000)
        with self.assertRaises(ArchiveError) as busy:
            restore(backups.path(created['name']), target)
        self.assertEqual(busy.exception.code, 'target_not_empty')

        with self.db.connect() as db:
            events = [row[0] for row in db.execute('SELECT action FROM security_events ORDER BY sequence')]
        self.assertEqual(events, ['backup.created', 'backup.verified'])

    def test_tampered_or_incomplete_backups_fail_verification_and_are_not_restored(self):
        doc = self.document(b'original bytes')
        backups = Backups(self.storage)
        path = backups.path(backups.create('admin')['name'])
        tampered = self.root / 'tampered.zip'
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(tampered, 'w') as target:
            for item in source.infolist():
                data = source.read(item.filename)
                target.writestr(item, b'changed bytes!' if item.filename.startswith('originals/') else data)
        report = verify_file(tampered)
        self.assertFalse(report['ok'])
        self.assertTrue(any('checksum mismatch' in p for p in report['problems']))
        with self.assertRaises(ArchiveError):
            restore(tampered, self.root / 'never')
        self.assertFalse((self.root / 'never').exists())
        partial = self.root / 'partial.zip'
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(partial, 'w') as target:
            for item in source.infolist():
                if item.filename.startswith('originals/'):
                    continue
                data = source.read(item.filename)
                if item.filename == 'manifest.json':
                    manifest = json.loads(data)
                    manifest['files'] = [f for f in manifest['files'] if not f['path'].startswith('originals/')]
                    data = json.dumps(manifest).encode()
                target.writestr(item, data)
        self.assertIn(f'original missing for document {doc}', verify_file(partial)['problems'])
        self.assertFalse(verify_file(self.root / 'nothing.zip')['ok'])

    def test_backup_refuses_when_an_original_is_damaged_and_names_are_validated(self):
        doc = self.document(b'good')
        (self.storage / 'originals' / f'{doc}/original.png').write_bytes(b'evil')
        backups = Backups(self.storage)
        with self.assertRaises(ArchiveError) as damaged:
            backups.create('admin')
        self.assertEqual(damaged.exception.code, 'backup_integrity')
        self.assertEqual(backups.list(), [])
        for name in ('../archive.sqlite3', 'x.zip', ''):
            with self.assertRaises(ArchiveError):
                backups.path(name)


class IntegrityTests(Archive):
    def test_reports_missing_damaged_and_orphan_originals_without_changing_anything(self):
        ok, missing, damaged = self.document(b'a'), self.document(b'b'), self.document(b'c')
        (self.storage / 'originals' / f'{missing}/original.png').unlink()
        (self.storage / 'originals' / f'{damaged}/original.png').write_bytes(b'x')
        orphan = self.storage / 'originals' / str(uuid.uuid4())
        orphan.mkdir()
        (orphan / 'upload.part').write_bytes(b'partial')
        report = integrity(self.storage, 'admin')
        self.assertFalse(report['ok'])
        self.assertEqual({(p['document_id'], p['problem']) for p in report['document_problems']},
                         {(missing, 'original_missing'), (damaged, 'checksum_mismatch')})
        self.assertEqual((report['orphan_folders'], report['partial_uploads']), ([orphan.name], [orphan.name]))
        self.assertEqual((report['database'], report['missing_triggers']), ('ok', []))
        self.assertTrue(orphan.exists())

    def test_clean_archive_passes(self):
        self.document(b'a')
        report = integrity(self.storage, 'admin')
        self.assertTrue(report['ok'])
        self.assertEqual(report['warnings'], 0)


class FastEditsTests(unittest.TestCase):
    def test_matches_the_canonical_research_implementation(self):
        import random
        from smartarchive.evaluation.metrics import levenshtein
        from smartarchive.operations.evaluation import fast_edits
        rng = random.Random(7)
        alphabet = 'ابتثجحخ دذرزسش'
        for _ in range(300):
            ref = ''.join(rng.choice(alphabet) for _ in range(rng.randint(0, 25)))
            hyp = ''.join(rng.choice(alphabet) for _ in range(rng.randint(0, 25)))
            edits = levenshtein(ref, hyp)
            self.assertEqual(fast_edits(ref, hyp), (edits.substitutions, edits.deletions, edits.insertions), (ref, hyp))
            self.assertEqual(fast_edits(ref.split(), hyp.split()),
                             tuple(vars(levenshtein(ref.split(), hyp.split())).values()))

    def test_a_full_page_is_measured_quickly(self):
        import time
        from smartarchive.operations.evaluation import fast_edits
        page = ('بسم الله الرحمن الرحيم قرار إداري رقم ' * 60)[:2000]
        started = time.perf_counter()
        fast_edits(page, page.replace('ا', 'أ', 40))
        self.assertLess(time.perf_counter() - started, 5)


class EvaluationTests(Archive):
    def run_with_text(self, doc_id: str, lines: list[str], confidence: float) -> str:
        run_id = str(uuid.uuid4())
        with self.db.connect() as db:
            db.execute("INSERT INTO ocr_runs(id,document_id,status,engine,languages,params,created_by,created_at,"
                       "pages_total,pages_done,review_required) VALUES (?,?,'ready','fake','ara','{}','admin',?,1,1,1)",
                       (run_id, doc_id, '2026-01-02T00:00:00'))
            db.execute('INSERT INTO page_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (run_id, 1, 100, 100, 300, 'metadata', '{}', 0.8, 'fast', 0, '[]', confidence, 1, 10))
            for index, line in enumerate(lines):
                db.execute('INSERT INTO ocr_lines VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (run_id, 1, index + 1, line, confidence, 0, 0, 1, 1, '[]'))
            PageTexts(self.db).index_run(db, run_id, doc_id)
        return run_id

    def test_ocr_post_editing_rates_use_the_corrected_text_as_reference(self):
        texts = PageTexts(self.db)
        low, high = self.document(b'1'), self.document(b'2')
        self.run_with_text(low, ['قرار ادري رقم'], 0.4)
        self.run_with_text(high, ['تقرير سنوي'], 0.9)
        texts.revise(self.db.get(low), 1, 'قرار إداري رقم', 0, '', 'reviewer')
        texts.revise(self.db.get(high), 1, 'تقرير سنوي شامل', 0, '', 'reviewer')
        texts.revise(self.db.get(low), 1, 'قرار إداري رقم ٥', 1, '', 'reviewer')  # latest version is the reference
        result = ocr_post_editing(self.db)
        self.assertEqual(result['summary']['pages'], 2)
        page = next(p for p in result['pages'] if p['document_id'] == low)
        # "قرار ادري رقم" -> "قرار إداري رقم ٥": ا→إ, missing ا, missing " ٥" (normalized-v1 keeps hamza forms)
        self.assertEqual((page['char_errors'], page['chars']), (4, 16))
        self.assertEqual(page['ocr_confidence'], 0.4)
        self.assertEqual(result['by_confidence'][0]['pages'], 1)
        self.assertIsNotNone(result['summary']['micro_cer'])

    def test_classification_accuracy_compares_shown_suggestion_with_human_label(self):
        service = Classifications(self.db)
        service.seed()
        docs = []
        for text in ('قرار إداري يقرر المادة الأولى يعمل به', 'السيد المدير المحترم نحيطكم علما ونرجو التكرم بالموافقة وتفضلوا بقبول فائق الاحترام', 'قصيدة'):
            doc = self.document(text.encode(), 'scan.png')
            with self.db.connect() as db:
                PageTexts._upsert(db, doc, 1, 'ocr', None, None, text)
            service.suggest(doc)
            docs.append(doc)
        service.decide(docs[0], 'decision', '', service.get(docs[0])['sequence'], 'r')   # agrees
        service.decide(docs[1], 'admin_form', '', service.get(docs[1])['sequence'], 'r')  # disagrees (was a letter)
        service.decide(docs[2], 'report', '', service.get(docs[2])['sequence'], 'r')     # classifier abstained
        result = classification_accuracy(self.db)['summary']
        self.assertEqual((result['labelled'], result['covered']), (3, 2))
        self.assertAlmostEqual(result['coverage'], 0.6667, places=3)
        self.assertEqual((result['accuracy_when_suggested'], result['accuracy_overall']), (0.5, 0.3333))
        confusion = classification_accuracy(self.db)['confusion']
        self.assertEqual(confusion['report'], {'abstain': 1})
        self.assertEqual(confusion['admin_form'], {'outgoing_letter': 1})


if __name__ == '__main__':
    unittest.main()
