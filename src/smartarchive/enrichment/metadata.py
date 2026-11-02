"""Rule-based extraction of archival metadata (`rules-v2`) with human correction.

v2 (Sprint 6, from the synthetic evaluation): a bare «من»/«إلى» label needs a colon; amounts prefer the grand
total over a subtotal or a table heading; a date may follow its value on mixed-direction lines; without a
«الموضوع» label the title of a decision («قرار ... بشأن ...»), contract, report or minutes gives the subject
(confidence 0.6-0.65); invisible direction marks inserted by OCR are ignored.

Fields: reference_number, date, sender, recipient, subject, amount. Each value keeps the page, the character
span in that page's text and a confidence: labelled values ("الموضوع: ...", "رقم الكتاب: ...") score 0.9,
unlabelled patterns (a bare date) 0.6. Dates are normalized to ISO (day-first, as in Arabic correspondence);
Hijri dates are kept as written with calendar "hijri".

Every extraction run and every human edit is a new append-only row. The current value of a field is the
latest human edit, otherwise the value of the latest extraction run. A re-extraction never overrides a person.
"""
from dataclasses import dataclass
import logging
import re
import uuid

from smartarchive.domain.documents import ArchiveError
from smartarchive.persistence.database import Database, now

log = logging.getLogger(__name__)
METHOD = 'rules-v2'
SYSTEM = 'system:metadata'
FIELDS = ('reference_number', 'date', 'sender', 'recipient', 'subject', 'amount')
# Values a constrained OCR corrector must never change automatically (project brief, section 12).
PROTECTED = ('reference_number', 'date', 'amount', 'sender', 'recipient')

DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
D = r'[0-9٠-٩۰-۹]'
SEP = r'\s*[:：\-–/]?\s*'
END = r'[^\n]{2,160}'
LABEL_COLON = r'[:：؛]'
AMOUNT = (r'[^\n0-9٠-٩۰-۹]{0,25}([0-9٠-٩۰-۹][0-9٠-٩۰-۹,\.٬٫]*\s*'
          r'(?:دينار|ريال|دولار|جنيه|درهم|ليرة|يورو)?)')
MONTHS = {name: number for number, names in enumerate([
    ('يناير', 'كانون الثاني', 'كانون ثاني'), ('فبراير', 'شباط'), ('مارس', 'آذار', 'اذار'), ('أبريل', 'ابريل', 'نيسان'),
    ('مايو', 'أيار', 'ايار'), ('يونيو', 'حزيران'), ('يوليو', 'تموز'), ('أغسطس', 'اغسطس', 'آب', 'اب'),
    ('سبتمبر', 'أيلول', 'ايلول'), ('أكتوبر', 'اكتوبر', 'تشرين الأول', 'تشرين الاول'),
    ('نوفمبر', 'تشرين الثاني', 'تشرين ثاني'), ('ديسمبر', 'كانون الأول', 'كانون الاول')], 1) for name in names}
MONTH_ALT = '|'.join(sorted(map(re.escape, MONTHS), key=len, reverse=True))
DATE = rf'{D}{{1,4}}\s*[/\-\.]\s*{D}{{1,2}}\s*[/\-\.]\s*{D}{{1,4}}(?:\s*هـ)?|{D}{{1,2}}\s+(?:{MONTH_ALT})\s+{D}{{4}}'
# Invisible direction marks that OCR inserts around numbers; replaced by spaces so offsets stay valid.
BIDI_MARKS = {code: ' ' for code in (0x200E, 0x200F, 0x061C, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067,
                                     0x2068, 0x2069)}

PATTERNS = {
    'subject': [(re.compile(rf'(?:^|\n)\s*(?:ال)?موضوع{SEP}({END})'), 0.9),
                # No «الموضوع:» label: the title of a decision, contract, report or minutes states it.
                (re.compile(r'(?:^|\n)[ \t]*(?:قرار[^\n]{0,40}?بشأن\s+|بشأن\s+)([^\n]{6,160})'), 0.65),
                (re.compile(r'(?:^|\n)[ \t]*((?:عقد|محضر اجتماع|تقرير فني|تقرير)\s[^\n]{6,150})'), 0.6)],
    'reference_number': [
        (re.compile(rf'(?:رقم\s*(?:الكتاب|القرار|العقد|الفاتورة|الصادر|الوارد|القيد|المرجع|المعاملة|النموذج)|'
                    rf'الرقم|المرجع|الإشارة|الاشارة|Ref\.?|No\.?){SEP}'
                    rf'((?:[A-Za-z\u0621-\u064A]{{1,6}}\s?[/\-\.]\s?)?{D}[{D[1:-1]}/\-\.A-Za-z\u0621-\u064A]{{0,30}})'), 0.9)],
    'date': [
        (re.compile(rf'(?:التاريخ|تاريخ(?:\s*(?:الكتاب|القرار|العقد|الفاتورة|الورود|الصدور|التحرير))?|Date){SEP}'
                    rf'({DATE})'), 0.9),
        # Mixed-direction lines: OCR can put the value before its label («١٥/٠٣/٢٠٢٦ التاريخ:»).
        (re.compile(rf'(?:^|\n)[ \t]*({DATE})[ \t]+ا?لتاريخ[ \t]*[:：؛]?[ \t]*(?=\n|$)'), 0.85),
        (re.compile(rf'(?<![0-9٠-٩])({D}{{1,2}}\s*[/\-\.]\s*{D}{{1,2}}\s*[/\-\.]\s*{D}{{4}}(?:\s*هـ)?|{D}{{4}}-{D}{{2}}-{D}{{2}}|'
                    rf'{D}{{1,2}}\s+(?:{MONTH_ALT})\s+{D}{{4}})'), 0.6)],
    # A bare «من» / «إلى» needs a colon (OCR often reads it as «؛»): wrapped body lines also start with them.
    'sender': [(re.compile(rf'(?:^|\n)\s*(?:(?:المرسل|صادر عن|الجهة المرسلة){SEP}|من\s*{LABEL_COLON}\s*)({END})'), 0.9)],
    'recipient': [(re.compile(rf'(?:^|\n)\s*(?:(?:المرسل إليه|المرسل اليه){SEP}|(?:إلى|الى)\s*{LABEL_COLON}\s*)({END})'), 0.9),
                  (re.compile(r'(?:^|\n)\s*(?:السيد|السيدة|حضرة)\s*/?\s*([^\n]{2,120}?)\s*(?:المحترم|المحترمة)'), 0.75)],
    # Grand total first, then a stated amount, then any sum (an invoice's «المجموع» is often a subtotal or
    # a table column heading).
    'amount': [(re.compile(rf'(?:{label}){AMOUNT}'), confidence) for label, confidence in (
        ('المبلغ الإجمالي|المبلغ الاجمالي|الإجمالي|الاجمالي|إجمالي|اجمالي|المجموع الكلي', 0.9),
        ('المبلغ', 0.85), ('المجموع', 0.7))],
}


@dataclass
class Found:
    field: str
    value: str
    normalized: str
    raw: str
    page_no: int
    start: int
    end: int
    confidence: float


def normalize_date(text: str) -> tuple[str, str]:
    """(normalized, calendar). ISO for valid Gregorian dates; Hijri and unparseable values are kept as written."""
    value = text.translate(DIGITS)
    if 'هـ' in value:
        numbers = re.findall(r'\d+', value)
        return '/'.join(numbers), 'hijri'
    match = re.fullmatch(r'\s*(\d{1,2})\s+(\S.*?)\s+(\d{4})\s*', value)
    if match and match.group(2) in MONTHS:
        day, month, year = int(match.group(1)), MONTHS[match.group(2)], int(match.group(3))
    else:
        parts = [int(p) for p in re.findall(r'\d+', value)]
        if len(parts) != 3:
            return value.strip(), 'unknown'
        if parts[0] > 31:
            year, month, day = parts
        else:
            day, month, year = parts
            year += 2000 if year < 100 else 0
    if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100:
        return f'{year:04d}-{month:02d}-{day:02d}', 'gregorian'
    return value.strip(), 'unknown'


def _clean(value: str) -> str:
    return ' '.join(value.strip(' \t:：-–،,.').split())[:200]


def extract(pages: list[tuple[int, str]]) -> dict[str, Found]:
    """First confident match per field, searching pages in order (headers usually sit on page 1)."""
    found: dict[str, Found] = {}
    for field, patterns in PATTERNS.items():
        best = None
        for page_no, text in pages:
            text = text.translate(BIDI_MARKS)
            for pattern, confidence in patterns:
                match = pattern.search(text)
                if match and (best is None or confidence > best.confidence):
                    raw = match.group(1)
                    value = _clean(raw)
                    if not value:
                        continue
                    normalized = value
                    if field == 'date':
                        normalized, calendar = normalize_date(value)
                        confidence = confidence if calendar != 'unknown' else min(confidence, 0.5)
                    elif field in ('reference_number', 'amount'):
                        normalized = value.translate(DIGITS).replace('٬', ',').replace('٫', '.')
                    best = Found(field, value, normalized, raw, page_no, match.start(1), match.end(1), confidence)
            if best and best.confidence >= 0.9:
                break
        if best:
            found[field] = best
    return found


class Metadata:
    def __init__(self, db: Database):
        self.db = db

    def run(self, document_id: str, actor: str = SYSTEM) -> dict:
        with self.db.connect() as db:
            if not db.execute('SELECT 1 FROM documents WHERE id=?', (document_id,)).fetchone():
                raise ArchiveError('not_found', 'المستند غير موجود.', 404)
            pages = [(row['page_no'], row['text']) for row in db.execute(
                'SELECT page_no, text FROM page_texts WHERE document_id=? ORDER BY page_no', (document_id,))]
        found = extract(pages)
        run, stamp = str(uuid.uuid4()), now()
        rows = []
        for field in FIELDS:
            item = found.get(field)
            rows.append((document_id, run, field, item.value if item else None, item.normalized if item else None,
                         item.raw if item else None, item.page_no if item else None, item.start if item else None,
                         item.end if item else None, item.confidence if item else None, 'extracted', METHOD, actor, stamp))
        with self.db.connect() as db:
            previous = self._extracted(db, document_id)
            if previous == {field: (found[field].value if field in found else None) for field in FIELDS}:
                return self.get(document_id)  # nothing changed since the last run: no new rows
            db.executemany('INSERT INTO metadata_values(document_id,run,field,value,normalized,raw,page_no,start_offset,'
                           'end_offset,confidence,source,method,actor,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        return self.get(document_id)

    def run_quietly(self, document_id: str, actor: str = SYSTEM):
        try:
            self.run(document_id, actor)
        except Exception:
            log.exception('Metadata extraction failed for %s', document_id)

    @staticmethod
    def _extracted(db, document_id: str) -> dict | None:
        last = db.execute("SELECT run FROM metadata_values WHERE document_id=? AND source='extracted'"
                          ' ORDER BY sequence DESC LIMIT 1', (document_id,)).fetchone()
        if not last:
            return None
        return {row['field']: row['value'] for row in db.execute(
            'SELECT field, value FROM metadata_values WHERE run=?', (last['run'],))}

    def get(self, document_id: str) -> dict:
        with self.db.connect() as db:
            rows = [dict(row) for row in db.execute(
                'SELECT * FROM metadata_values WHERE document_id=? ORDER BY sequence', (document_id,))]
        last_run = next((row['run'] for row in reversed(rows) if row['source'] == 'extracted'), None)
        fields = {}
        for field in FIELDS:
            human = [row for row in rows if row['field'] == field and row['source'] == 'human']
            machine = next((row for row in rows if row['run'] == last_run and row['field'] == field), None)
            current = human[-1] if human else machine
            fields[field] = {'field': field, 'value': current['value'] if current else None,
                             'normalized': current['normalized'] if current else None,
                             'source': current['source'] if current and current['value'] is not None else None,
                             'confidence': current['confidence'] if current else None,
                             'page_no': current['page_no'] if current else None,
                             'start': current['start_offset'] if current else None,
                             'end': current['end_offset'] if current else None,
                             'actor': current['actor'] if current else None,
                             'updated_at': current['created_at'] if current else None,
                             'extracted_value': machine['value'] if machine else None,
                             'protected': field in PROTECTED,
                             'history': len([row for row in rows if row['field'] == field])}
        return {'document_id': document_id, 'method': METHOD, 'extracted': last_run is not None, 'fields': fields}

    def edit(self, document_id: str, field: str, value: str | None, actor: str) -> dict:
        if field not in FIELDS:
            raise ArchiveError('unknown_field', 'حقل بيانات وصفية غير معروف.', 422)
        value = ' '.join((value or '').split())[:200] or None
        normalized = value
        if value and field == 'date':
            normalized, calendar = normalize_date(value)
            if calendar == 'unknown':
                raise ArchiveError('invalid_date', 'صيغة التاريخ غير مفهومة (مثال: 2026-03-15 أو 15/03/2026).', 422)
        elif value and field in ('reference_number', 'amount'):
            normalized = value.translate(DIGITS)
        current = self.get(document_id)['fields'][field]
        if current['value'] == value:
            raise ArchiveError('unchanged', 'القيمة لم تتغير.', 422)
        with self.db.connect() as db:
            db.execute('INSERT INTO metadata_values(document_id,run,field,value,normalized,raw,page_no,start_offset,'
                       'end_offset,confidence,source,method,actor,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (document_id, str(uuid.uuid4()), field, value, normalized, None, None, None, None, 1.0, 'human',
                        'human', actor, now()))
            self.db._event(db, document_id, 'metadata.edited',
                           {'field': field, 'from': current['value'], 'to': value}, actor)
        return self.get(document_id)

    def values(self, document_id: str) -> dict[str, str]:
        """Current normalized values only (for relations, classification and search)."""
        return {field: item['normalized'] for field, item in self.get(document_id)['fields'].items() if item['normalized']}
