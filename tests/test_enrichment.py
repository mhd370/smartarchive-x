"""Folders, metadata extraction/correction and duplicate/version detection (Sprint 5)."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from smartarchive.domain.documents import ArchiveError
from smartarchive.enrichment.duplicates import Relations
from smartarchive.enrichment.metadata import Metadata, extract, normalize_date
from smartarchive.persistence.database import Database
from smartarchive.search.pages import PageTexts
from smartarchive.services.folders import Folders

LETTER = '''وزارة الأشغال العامة
الرقم: ص/١٢٣/٢٠٢٦
التاريخ: ١٥/٠٣/٢٠٢٦
إلى: مديرية الموارد البشرية
من: دائرة الشؤون الإدارية
الموضوع: تمديد مدة المشروع لمدة ٩٠ يوما
تحية طيبة وبعد، نحيطكم علما بأنه تقرر تمديد مدة تنفيذ مشروع صيانة المباني الحكومية في المحافظة
لمدة تسعين يوما إضافية اعتبارا من تاريخه وذلك بسبب تأخر توريد المواد الأساسية من المورد المعتمد
ويرجى التكرم باتخاذ ما يلزم لتعديل الجداول الزمنية وإبلاغ الجهات المعنية بذلك مع الشكر والتقدير'''


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Database(Path(temp.name) / 'archive.sqlite3')
        self.db.initialize()

    def document(self, text: str | None = None, sha: str | None = None, name='scan.png') -> str:
        doc = str(uuid.uuid4())
        with self.db.connect() as db:
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (doc, name, 10, 'image/png', sha or uuid.uuid4().hex * 2, doc + '/original.png', 1, 'ready',
                        'OCR_COMPLETED', '2026-01-01T00:00:00', '2026-01-01T00:00:00'))
            if text is not None:
                PageTexts._upsert(db, doc, 1, 'ocr', None, None, text)
        return doc


class FolderTests(Base):
    def test_tree_paths_counts_filing_and_listing_with_subfolders(self):
        folders = Folders(self.db)
        root = folders.create('الشؤون المالية', None, 'admin')
        child = folders.ensure_path('الشؤون المالية/فواتير 2026', 'import')
        self.assertEqual(child['path'], 'الشؤون المالية/فواتير 2026')
        self.assertEqual(folders.ensure_path('الشؤون المالية/فواتير 2026', 'import')['id'], child['id'])
        with self.assertRaises(ArchiveError):
            folders.create('الشؤون المالية', None, 'admin')
        for bad in ('', 'a/b', '..'):
            with self.assertRaises(ArchiveError):
                folders.create(bad, None, 'admin')
        doc, other = self.document(), self.document()
        folders.file(doc, child['id'], 'archivist')
        folders.file(other, root['id'], 'archivist')
        tree = {item['path']: item for item in folders.tree()}
        self.assertEqual((tree['الشؤون المالية']['documents'], tree['الشؤون المالية']['total_documents']), (1, 2))
        self.assertEqual(self.db.list('', None, None, 10, 0, folder=root['id'])['total'], 2)
        self.assertEqual(self.db.list('', None, None, 10, 0, folder=child['id'])['total'], 1)
        self.assertEqual(self.db.list('', None, None, 10, 0, folder=child['id'])['items'][0]['folder_path'], child['path'])
        folders.file(doc, None, 'archivist')
        self.assertIsNone(folders.of(doc))
        moves = [e['details'] for e in self.db.events(doc) if e['action'] == 'document.filed']
        self.assertEqual(moves, [{'from': None, 'to': child['path']}, {'from': child['path'], 'to': None}])

    def test_similar_folder_names_are_not_confused_by_prefix(self):
        folders = Folders(self.db)
        a, ab = folders.create('عقود', None, 'x'), folders.create('عقود قديمة', None, 'x')
        folders.file(self.document(), ab['id'], 'x')
        self.assertEqual(self.db.list('', None, None, 10, 0, folder=a['id'])['total'], 0)


class MetadataTests(Base):
    def test_extracts_labelled_fields_with_spans_and_normalized_values(self):
        found = extract([(1, LETTER)])
        self.assertEqual(found['reference_number'].normalized, 'ص/123/2026')
        self.assertEqual(found['date'].normalized, '2026-03-15')
        self.assertEqual((found['sender'].value, found['recipient'].value), ('دائرة الشؤون الإدارية', 'مديرية الموارد البشرية'))
        self.assertEqual(found['subject'].value, 'تمديد مدة المشروع لمدة ٩٠ يوما')
        self.assertEqual(LETTER[found['subject'].start:found['subject'].end].strip(), found['subject'].value)
        invoice = extract([(1, 'فاتورة\nرقم الفاتورة: INV-2026-77\nبتاريخ 3 آذار 2026\nالمجموع الكلي: ١٬٢٥٠٫٥٠ دينار')])
        self.assertEqual(invoice['reference_number'].value, 'INV-2026-77')
        self.assertEqual(invoice['date'].normalized, '2026-03-03')
        self.assertEqual(invoice['amount'].normalized, '1,250.50 دينار')
        self.assertEqual(extract([(1, 'نص بلا بيانات')]), {})

    def test_dates(self):
        self.assertEqual(normalize_date('١٤٤٧/٩/١٢ هـ'), ('1447/9/12', 'hijri'))
        self.assertEqual(normalize_date('2026-02-01'), ('2026-02-01', 'gregorian'))
        self.assertEqual(normalize_date('31/12/26'), ('2026-12-31', 'gregorian'))
        self.assertEqual(normalize_date('45/13/2026')[1], 'unknown')

    def test_human_edits_win_over_re_extraction_and_history_is_append_only(self):
        service = Metadata(self.db)
        doc = self.document(LETTER)
        first = service.run(doc)
        self.assertEqual(first['fields']['subject']['source'], 'extracted')
        self.assertTrue(first['fields']['reference_number']['protected'])
        edited = service.edit(doc, 'subject', 'تمديد مشروع صيانة المباني', 'reviewer1')
        self.assertEqual((edited['fields']['subject']['value'], edited['fields']['subject']['actor']),
                         ('تمديد مشروع صيانة المباني', 'reviewer1'))
        with self.db.connect() as db:
            PageTexts._upsert(db, doc, 1, 'review', None, 1, LETTER.replace('١٢٣', '٧٧٧'))
        again = service.run(doc)
        self.assertEqual(again['fields']['subject']['value'], 'تمديد مشروع صيانة المباني')
        self.assertEqual(again['fields']['reference_number']['normalized'], 'ص/777/2026')
        self.assertEqual(again['fields']['subject']['extracted_value'], 'تمديد مدة المشروع لمدة ٩٠ يوما')
        def rows():
            with self.db.connect() as db:
                return db.execute('SELECT COUNT(*) FROM metadata_values').fetchone()[0]
        count = rows()
        service.run(doc)  # unchanged text: no new rows
        self.assertEqual(rows(), count)
        with self.assertRaises(ArchiveError):
            service.edit(doc, 'date', 'غدا', 'r')
        with self.assertRaises(ArchiveError):
            service.edit(doc, 'colour', 'x', 'r')
        with self.db.connect() as db, self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE metadata_values SET value='x'")
        self.assertIn('metadata.edited', [e['action'] for e in self.db.events(doc)])


class RelationTests(Base):
    def test_exact_near_and_version_relations_and_review(self):
        metadata = Metadata(self.db)
        relations = Relations(self.db, metadata)
        original = self.document(LETTER, sha='a' * 64)
        exact = self.document(LETTER, sha='a' * 64)
        near = self.document(LETTER.replace('مع الشكر والتقدير', 'مع الشكر'))
        version = self.document(LETTER.split('تحية')[0] + 'تحية طيبة وبعد، نود إعلامكم بإلغاء التمديد السابق '
                                'وإعادة الجدول الزمني إلى ما كان عليه بسبب وصول المواد في موعدها المحدد من المورد '
                                'بعد التنسيق مع اللجنة الفنية المختصة بالمتابعة والإشراف على التنفيذ')
        unrelated = self.document('تقرير فني عن أداء شبكة المياه في المنطقة الشمالية خلال الربع الأول من العام '
                                  'ويتضمن نتائج القياسات والتوصيات المقترحة لتحسين كفاءة الضخ وتقليل الفاقد')
        for doc in (original, exact, near, version, unrelated):
            metadata.run(doc)
            relations.detect(doc)
        kinds = {(r['kind'], r['other_id']) for r in relations.of(original)}
        self.assertIn(('exact_duplicate', exact), kinds)
        self.assertIn(('near_duplicate', near), kinds)
        self.assertNotIn(unrelated, {other for _, other in kinds})
        self.assertEqual(len([r for r in relations.of(exact) if r['kind'] == 'exact_duplicate']), 1)
        version_links = [r for r in relations.of(version) if r['kind'] == 'version_of']
        self.assertTrue(version_links, relations.of(version))
        self.assertIn('reference_number', version_links[0]['evidence']['shared_fields'])
        relation = relations.of(original)[0]
        relations.review(relation['id'], 'confirmed', 'reviewer1')
        with self.assertRaises(ArchiveError):
            relations.review(relation['id'], 'confirmed', 'reviewer1')
        self.assertIn('relation.confirmed', [e['action'] for e in self.db.events(original)])
        self.assertEqual(relations.ensure_fingerprinted(), 0)


if __name__ == '__main__':
    unittest.main()
