r"""Generate a documented synthetic Arabic institutional corpus with exact ground truth.

  .\.venv\Scripts\python.exe tools/synth_corpus.py --documents 150 --out data\synthetic\corpus_v1

Why: no authorized institutional documents are available. The brief's eight document types are produced from
templates with fictional organizations, people, numbers and dates, rendered as real PDFs (PyMuPDF HTML layout
with Arabic shaping) and, for part of the corpus, turned into degraded scans with the project's seeded
degradation levels (clean / mild / medium / severe). Everything is reproducible from --seed.

Output:
  archive/<department>/<year>/<file>   files to import (tools/import_tree.py); folders follow departments and
                                        years, not document types, so folder evidence is informative but not a label
  ground_truth/<doc_id>.json            type, group, metadata, relations, and per page: text in reading order and
                                        blocks (header, title, metadata, paragraph, table, signature, stamp, footer)
                                        with normalized boxes and reading order
  queries.json                          search queries with their relevant documents/pages (from known metadata)
  manifest.json                         one entry per file: sha256, doc_id, type, layout, quality level, relations
  README.md                             what is synthetic and how it was made

Results on this corpus must be reported as synthetic and kept separate from results on real public datasets.
"""
import argparse
from datetime import date, timedelta
import hashlib
import html
import io
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

GENERATOR = 'synth-corpus-v1'
A4 = (595.0, 842.0)
MARGIN = 50.0
FONT_FILES = {'arial': 'arial.ttf', 'times': 'times.ttf', 'tahoma': 'tahoma.ttf', 'trado': 'trado.ttf',
              'simpo': 'simpo.ttf', 'majalla': 'majalla.ttf'}
DIGITS_AR = str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')

# ---------------------------------------------------------------------------------------------- vocabulary
FIRST = ['محمد', 'أحمد', 'خالد', 'عمر', 'يوسف', 'سامي', 'ليلى', 'مريم', 'هالة', 'رنا', 'فاطمة', 'زياد', 'طارق', 'نور',
         'سلمى', 'باسل', 'هادي', 'ريم', 'علي', 'إبراهيم', 'جميلة', 'وسيم', 'منى', 'عبد الله', 'كريم', 'لينا']
FAMILY = ['الحسيني', 'العلي', 'النجار', 'الخطيب', 'الزعبي', 'الشامي', 'الأحمد', 'المصري', 'الحلبي', 'السيد', 'الكردي',
          'العمري', 'الدباغ', 'الصالح', 'القاسم', 'البيطار', 'الحداد', 'الرفاعي', 'الشريف', 'الجابري']
PROVINCE = 'محافظة الوادي الأخضر'  # fictional
OWN = 'مديرية الخدمات العامة'  # the archiving institution (fictional)
DEPARTMENTS = {'admin': 'الشؤون الإدارية', 'finance': 'الشؤون المالية', 'legal': 'الشؤون القانونية',
               'tech': 'الدائرة الفنية', 'hr': 'الموارد البشرية', 'office': 'مكتب المدير العام'}
EXTERNAL = ['وزارة الأشغال العامة', 'مديرية التربية', 'المؤسسة العامة للمياه', 'بلدية المدينة', 'غرفة التجارة',
            'مديرية الصحة', 'هيئة التخطيط والتعاون الدولي', 'المؤسسة العامة للكهرباء', 'جامعة الوادي']
COMPANIES = ['شركة النخيل للمقاولات', 'شركة الأفق للتوريدات', 'مؤسسة البناء الحديث', 'شركة الرواد للتقنية',
             'شركة الفرات للخدمات الهندسية', 'مكتب الضياء للاستشارات', 'شركة المنارة للتجهيزات المكتبية']
PROJECTS = ['صيانة المباني الحكومية', 'تأهيل شبكة المياه', 'إنارة الطرق الرئيسية', 'تحديث أنظمة الأرشفة',
            'ترميم المدارس', 'توسعة مركز الخدمات', 'تجهيز قاعة الاجتماعات', 'تطوير الموقع الإلكتروني']
ITEMS = [('أوراق طباعة A4', 'رزمة'), ('حبر طابعة', 'عبوة'), ('حاسوب مكتبي', 'جهاز'), ('كرسي مكتبي', 'قطعة'),
         ('خزانة ملفات', 'قطعة'), ('ماسح ضوئي', 'جهاز'), ('مصابيح إنارة', 'قطعة'), ('أنابيب مياه', 'متر'),
         ('إسمنت', 'كيس'), ('دهان', 'علبة'), ('قرص تخزين', 'قطعة'), ('طاولة اجتماعات', 'قطعة')]
CURRENCY = 'دينار'
FILLER = ['وقد تمت مراجعة الموضوع من قبل اللجنة المختصة وفق الأصول المتبعة.',
          'ويأتي ذلك في إطار حرص المديرية على تحسين مستوى الخدمات المقدمة للمواطنين.',
          'مع ضرورة التقيد بالتعليمات النافذة والإجراءات المعتمدة في هذا الشأن.',
          'على أن يتم إعلام الجهات ذات العلاقة بأي مستجدات في حينها.',
          'وقد روعي في ذلك تحقيق المصلحة العامة وضمان استمرارية العمل دون انقطاع.',
          'كما تم التنسيق مع الدوائر المعنية لتوفير المتطلبات اللازمة للتنفيذ.',
          'وتجدر الإشارة إلى أن الكلفة التقديرية تقع ضمن المخصصات المرصودة في الموازنة.',
          'ويتم حفظ نسخة من هذه الوثيقة في الملف الخاص بالمشروع للرجوع إليها عند الحاجة.',
          'وفي حال وجود أي ملاحظات يرجى إبلاغنا بها خلال المدة المحددة.',
          'وقد أظهرت المتابعة الدورية التزاماً مقبولاً بالمواصفات المطلوبة.']

TYPES = {  # type: (group, department weights, layout choices)
    'incoming_letter': ('administrative', ['office', 'admin', 'tech', 'hr'], ['simple']),
    'outgoing_letter': ('administrative', ['office', 'admin', 'tech', 'finance'], ['simple']),
    'decision': ('administrative', ['office', 'hr', 'admin'], ['simple']),
    'admin_form': ('administrative', ['hr', 'admin'], ['tabular']),
    'minutes': ('administrative', ['office', 'tech', 'admin'], ['simple', 'multi_column']),
    'contract': ('legal', ['legal', 'finance'], ['simple']),
    'invoice': ('financial', ['finance'], ['tabular']),
    'report': ('technical', ['tech', 'office'], ['multi_column', 'simple']),
}


def person(rng):
    return f'{rng.choice(FIRST)} {rng.choice(FAMILY)}'


def arabic(number) -> str:
    return str(number).translate(DIGITS_AR)


def fmt_date(day: date, rng) -> str:
    style = rng.random()
    if style < 0.5:
        return arabic(f'{day.day:02d}/{day.month:02d}/{day.year}')
    if style < 0.8:
        return f'{day.day:02d}/{day.month:02d}/{day.year}'
    months = ['كانون الثاني', 'شباط', 'آذار', 'نيسان', 'أيار', 'حزيران', 'تموز', 'آب', 'أيلول', 'تشرين الأول',
              'تشرين الثاني', 'كانون الأول']
    return f'{day.day} {months[day.month - 1]} {day.year}'


# ---------------------------------------------------------------------------------------------- content
def content(kind: str, rng, number: str, day: date, own_department: str) -> dict:
    """Blocks of text (logical order) and true metadata for one document of the given type."""
    project, company, other = rng.choice(PROJECTS), rng.choice(COMPANIES), rng.choice(EXTERNAL)
    days = rng.choice([30, 45, 60, 90, 120])
    signer = person(rng)
    meta = {'reference_number': number, 'date': day.isoformat(), 'sender': None, 'recipient': None, 'subject': None,
            'amount': None}
    blocks: list[tuple[str, str]] = []
    header = f'{PROVINCE}\n{OWN}\n{own_department}'
    if kind in ('incoming_letter', 'outgoing_letter'):
        incoming = kind == 'incoming_letter'
        sender = other if incoming else f'{OWN} - {own_department}'
        recipient = f'{OWN} - {own_department}' if incoming else other
        subject = rng.choice([f'تمديد مدة مشروع {project}', f'طلب تزويدنا ببيانات مشروع {project}',
                              f'تسمية ممثل عن الدائرة في لجنة {project}', f'الموافقة على صرف مستحقات {company}',
                              f'عقد اجتماع تنسيقي بخصوص {project}'])
        meta.update(sender=sender, recipient=recipient, subject=subject)
        if incoming:
            header = f'{other}\nالديوان العام'
        label = 'رقم الوارد' if incoming and rng.random() < 0.4 else ('رقم الصادر' if not incoming and rng.random() < 0.4 else 'الرقم')
        blocks += [('header', header),
                   ('metadata', f'{label}: {number}\nالتاريخ: {fmt_date(day, rng)}'),
                   ('metadata', f'من: {sender}\nإلى: {recipient}'),
                   ('title', f'الموضوع: {subject}'),
                   ('paragraph', 'تحية طيبة وبعد،'),
                   ('paragraph', rng.choice([
                       f'إشارة إلى كتابكم رقم {arabic(rng.randint(10, 900))} بتاريخ سابق، نحيطكم علماً بأنه تمت دراسة '
                       f'الموضوع من قبل الجهات المختصة، وتقرر تمديد مدة تنفيذ مشروع {project} لمدة {arabic(days)} يوماً '
                       f'إضافية اعتباراً من تاريخه، وذلك بسبب تأخر توريد المواد الأساسية من {company}.',
                       f'نرجو التكرم بتزويدنا بالبيانات التفصيلية المتعلقة بمشروع {project}، بما في ذلك نسب الإنجاز '
                       f'والمبالغ المصروفة حتى تاريخه، وذلك خلال مدة أقصاها {arabic(rng.randint(5, 15))} أيام من تاريخ '
                       f'استلام هذا الكتاب، لاستكمال إعداد التقرير الدوري المطلوب.',
                       f'يسرنا إعلامكم بأنه تمت الموافقة على مشاركة ممثل عن {own_department} في اللجنة المشكلة لمتابعة '
                       f'مشروع {project}، وقد تم تسمية السيد {person(rng)} لهذه المهمة، على أن يتم التنسيق معه مباشرة.'])),
                   ('paragraph', rng.choice(['يرجى التكرم بالاطلاع واتخاذ ما يلزم.', 'وتفضلوا بقبول فائق الاحترام.',
                                             'شاكرين لكم حسن تعاونكم.'])),
                   ('signature', f'{signer}\n{"مدير " + own_department if not incoming else "المدير العام"}')]
    elif kind == 'decision':
        subject = rng.choice([f'تشكيل لجنة لمتابعة مشروع {project}', f'تكليف السيد {person(rng)} بمهام رئيس قسم',
                              f'منح إجازة إدارية للعاملين في {own_department}', f'اعتماد الجدول الزمني لمشروع {project}'])
        meta.update(sender=f'{OWN}', subject=subject)
        blocks += [('header', header),
                   ('metadata', f'رقم القرار: {number}\nالتاريخ: {fmt_date(day, rng)}'),
                   ('title', f'قرار إداري بشأن {subject}'),
                   ('paragraph', f'إن المدير العام، بناءً على الصلاحيات المخولة له بموجب النظام الداخلي، واستناداً '
                                 f'إلى مقتضيات المصلحة العامة، يقرر ما يلي:'),
                   ('paragraph', f'المادة الأولى: {subject}، على أن تباشر المهام اعتباراً من تاريخ صدور هذا القرار.'),
                   ('paragraph', f'المادة الثانية: تتولى الجهة المعنية رفع تقرير دوري كل {arabic(rng.choice([15, 30]))} '
                                 f'يوماً عن سير العمل إلى مكتب المدير العام.'),
                   ('paragraph', 'المادة الثالثة: يبلغ هذا القرار إلى الجهات المختصة للتنفيذ، ويعمل به من تاريخه.'),
                   ('signature', f'{signer}\nالمدير العام')]
    elif kind == 'admin_form':
        form = rng.choice(['نموذج طلب إجازة', 'نموذج طلب صرف مستلزمات', 'استمارة تحديث بيانات موظف'])
        employee = person(rng)
        meta.update(sender=employee, recipient=own_department, subject=form)
        rows = [('الاسم الكامل', employee), ('الرقم الوظيفي', arabic(rng.randint(1000, 9999))), ('القسم', own_department),
                ('تاريخ الطلب', fmt_date(day, rng)), ('سبب الطلب', rng.choice(['ظروف عائلية', 'استكمال إجراءات رسمية',
                                                                             'احتياجات العمل اليومية'])),
                ('المدة / الكمية', arabic(rng.randint(1, 14)))]
        blocks += [('header', header), ('metadata', f'رقم النموذج: {number}'), ('title', form),
                   ('table', json.dumps(rows, ensure_ascii=False)),
                   ('paragraph', 'أتعهد بصحة المعلومات الواردة أعلاه. توقيع مقدم الطلب: ..................'),
                   ('paragraph', 'خاص بالإدارة: يعبأ من قبل الموظف المختص بعد التدقيق.'),
                   ('signature', f'{signer}\nرئيس القسم')]
    elif kind == 'minutes':
        committee = f'لجنة متابعة مشروع {project}'
        meta.update(subject=f'محضر اجتماع {committee}', sender=own_department)
        members = [person(rng) for _ in range(rng.randint(3, 5))]
        blocks += [('header', header), ('metadata', f'رقم المحضر: {number}\nالتاريخ: {fmt_date(day, rng)}'),
                   ('title', f'محضر اجتماع {committee}'),
                   ('paragraph', f'انعقد اجتماع اللجنة في مقر {own_department} برئاسة السيد {members[0]}، '
                                 f'وبحضور السادة: {"، ".join(members[1:])}.'),
                   ('paragraph', 'جدول الأعمال: مراجعة نسب الإنجاز، ومناقشة المعوقات، وتحديد الخطوات القادمة.'),
                   ('paragraph', f'ناقش المجتمعون التقرير المقدم من {company}، وتبين أن نسبة الإنجاز بلغت '
                                 f'{arabic(rng.randint(20, 95))}٪، وأن التأخير يعود إلى صعوبات في التوريد.'),
                   ('paragraph', f'وبعد المداولة تقرر ما يلي: أولاً متابعة التوريد أسبوعياً، ثانياً رفع توصية بتمديد '
                                 f'المدة {arabic(days)} يوماً، ثالثاً عقد الاجتماع القادم بعد أسبوعين.'),
                   ('signature', f'{members[0]}\nرئيس اللجنة')]
    elif kind == 'contract':
        value = rng.randint(5, 400) * 1000
        meta.update(subject=f'عقد {rng.choice(["توريد", "تنفيذ أعمال", "تقديم خدمات"])} لمشروع {project}',
                    sender=OWN, recipient=company, amount=f'{value:,} {CURRENCY}')
        blocks += [('header', header), ('metadata', f'رقم العقد: {number}\nالتاريخ: {fmt_date(day, rng)}'),
                   ('title', meta['subject']),
                   ('paragraph', f'إنه في يوم {fmt_date(day, rng)} تم الاتفاق بين كل من: الطرف الأول {OWN} ويمثلها '
                                 f'السيد {signer}، والطرف الثاني {company} ويمثلها السيد {person(rng)}.'),
                   ('paragraph', f'البند الأول: يلتزم الطرف الثاني بتنفيذ الأعمال المتعلقة بمشروع {project} وفق '
                                 f'المواصفات الفنية المرفقة والتي تعد جزءاً لا يتجزأ من هذا العقد.'),
                   ('paragraph', f'البند الثاني: قيمة العقد الإجمالية {arabic(f"{value:,}")} {CURRENCY} تدفع على '
                                 f'{arabic(rng.choice([2, 3, 4]))} دفعات بحسب نسب الإنجاز المعتمدة.'),
                   ('paragraph', f'البند الثالث: مدة العقد {arabic(days)} يوماً تبدأ من تاريخ توقيعه، ويحق للطرف الأول '
                                 f'فرض غرامة تأخير عن كل يوم تأخير.'),
                   ('paragraph', 'البند الرابع: يخضع هذا العقد للأنظمة النافذة، ويتم حل الخلافات ودياً بين الطرفين.'),
                   ('signature', f'الطرف الأول: {signer}\nالطرف الثاني: {company}')]
    elif kind == 'invoice':
        lines, total = [], 0
        for name, unit in rng.sample(ITEMS, rng.randint(3, 6)):
            quantity, price = rng.randint(1, 40), rng.randint(2, 300)
            lines.append((name, unit, quantity, price, quantity * price))
            total += quantity * price
        tax = round(total * 0.1)
        meta.update(sender=company, recipient=f'{OWN} - {DEPARTMENTS["finance"]}', subject=f'فاتورة {company}',
                    amount=f'{total + tax:,} {CURRENCY}')
        rows = [('الصنف', 'الوحدة', 'الكمية', 'سعر الوحدة', 'المجموع')] + \
               [(name, unit, arabic(q), arabic(p), arabic(t)) for name, unit, q, p, t in lines]
        blocks += [('header', f'{company}\nسجل تجاري {arabic(rng.randint(10000, 99999))}'),
                   ('metadata', f'رقم الفاتورة: {number}\nالتاريخ: {fmt_date(day, rng)}'),
                   ('metadata', f'إلى: {meta["recipient"]}'),
                   ('title', 'فاتورة'),
                   ('table', json.dumps(rows, ensure_ascii=False)),
                   ('paragraph', f'المجموع: {arabic(f"{total:,}")} {CURRENCY}\nضريبة ١٠٪: {arabic(f"{tax:,}")} {CURRENCY}\n'
                                 f'الإجمالي: {arabic(f"{total + tax:,}")} {CURRENCY}'),
                   ('signature', f'{person(rng)}\nالمحاسب')]
    else:  # report
        subject = f'تقرير فني حول {rng.choice(["سير العمل في", "تقييم أداء", "نتائج الكشف على"])} مشروع {project}'
        meta.update(subject=subject, sender=own_department)
        blocks += [('header', header), ('metadata', f'رقم التقرير: {number}\nالتاريخ: {fmt_date(day, rng)}'),
                   ('title', subject),
                   ('paragraph', f'الملخص: يعرض هذا التقرير نتائج المتابعة الميدانية لمشروع {project} خلال الفترة '
                                 f'الماضية، ويحلل نسب الإنجاز والمعوقات، ويقدم التوصيات اللازمة.'),
                   ('paragraph', f'المنهجية: اعتمد فريق العمل على الزيارات الميدانية ومراجعة الوثائق المقدمة من '
                                 f'{company}، إضافة إلى مقابلات مع المهندسين المشرفين.'),
                   ('paragraph', f'النتائج: بلغت نسبة الإنجاز {arabic(rng.randint(30, 95))}٪، وتبين وجود تأخير في '
                                 f'{rng.choice(["توريد المواد", "أعمال التمديدات", "الأعمال الإنشائية"])}، كما لوحظ '
                                 f'التزام جيد بمعايير السلامة.'),
                   ('paragraph', 'التحليل: تعود أسباب التأخير إلى عوامل خارجية تتعلق بالأسواق، وإلى نقص في عدد '
                                 'العمال المهرة خلال بعض المراحل.'),
                   ('paragraph', f'التوصيات: تمديد المدة {arabic(days)} يوماً، وتعزيز الإشراف الأسبوعي، ورفع تقرير '
                                 f'متابعة خلال شهر.'),
                   ('signature', f'{signer}\nمهندس مشرف')]
    # institutional filler sentences: realistic page lengths, some documents run to a second page
    extra = {'report': (2, 7), 'contract': (1, 5), 'minutes': (1, 4)}.get(kind, (0, 2))
    count = rng.randint(*extra)
    if count:
        at = next(i for i, (k, _) in enumerate(blocks) if k == 'signature')
        for _ in range(count):
            blocks.insert(at, ('paragraph', ' '.join(rng.sample(FILLER, rng.randint(2, 4)))))
            at += 1
    blocks.append(('footer', f'{OWN} - {PROVINCE} - هاتف {arabic(rng.randint(2000000, 2999999))}'))
    return {'blocks': blocks, 'metadata': meta}


# ---------------------------------------------------------------------------------------------- rendering
class Renderer:
    def __init__(self, fonts_dir: Path | None):
        import pymupdf
        self.pymupdf = pymupdf
        self.archive = pymupdf.Archive(str(fonts_dir)) if fonts_dir and fonts_dir.is_dir() else None
        self.fonts = [name for name, file in FONT_FILES.items() if fonts_dir and (fonts_dir / file).exists()]
        self.scratch = pymupdf.open()

    def css(self, font: str | None, size: float) -> str:
        face = f'@font-face {{font-family: doc; src: url({FONT_FILES[font]});}}' if font else ''
        family = 'doc, sans-serif' if font else 'sans-serif'
        # MuPDF: dir="rtl" on each paragraph gives right alignment and correct punctuation; adding
        # text-align:right on top of rtl flips it to the left, so only centring is set explicitly.
        return (f'{face} * {{font-family: {family}; font-size: {size}pt; line-height: 1.45;}} '
                '.c {text-align: center;} .b {font-weight: bold;} p {margin: 0 0 2px 0;} '
                'table {border-collapse: collapse; width: 100%;} td {border: 0.8px solid #333; padding: 3px 5px;}')

    def html(self, kind: str, text: str) -> str:
        if kind == 'table':
            rows = json.loads(text)
            # MuPDF lays out tables left to right even with dir="rtl" (and adds a stray column), so the
            # logical first column is written last and each cell is right-to-left on its own.
            count = max(len(row) for row in rows)
            first = 34 if count > 2 else 50
            widths = [first] + [round((100 - first) / (count - 1), 1)] * (count - 1)
            cells = ''.join('<tr>' + ''.join(f'<td dir="rtl" style="width: {widths[i]}%">{html.escape(str(row[i]))}</td>'
                                             for i in reversed(range(len(row)))) + '</tr>' for row in rows)
            return f'<table>{cells}</table>'
        cls = {'header': 'c b', 'title': 'c b', 'footer': 'c'}.get(kind, '')
        return ''.join(f'<p dir="rtl" class="{cls}">{html.escape(line)}</p>' for line in text.split('\n'))

    def height(self, block_html: str, width: float, css: str) -> float:
        page = self.scratch.new_page(width=width + 10, height=2000)
        spare, _ = page.insert_htmlbox(self.pymupdf.Rect(0, 0, width, 2000), block_html, css=css, archive=self.archive,
                                       scale_low=1)
        self.scratch.delete_page(-1)
        return 2000 - spare if spare >= 0 else 2000

    def render(self, blocks: list[tuple[str, str]], layout: str, rng, stamp_text: str) -> tuple[bytes, list[dict]]:
        pymupdf = self.pymupdf
        font = rng.choice(self.fonts) if self.fonts and rng.random() < 0.8 else None
        size = rng.choice([10.5, 11, 11.5, 12])
        css = self.css(font, size)
        doc = pymupdf.open()
        pages: list[dict] = []
        width, height = A4
        full = width - 2 * MARGIN
        page, y, page_blocks, order = None, 0.0, [], 0

        def new_page():
            nonlocal page, y, page_blocks
            if page is not None:
                pages.append({'blocks': page_blocks})
            page = doc.new_page(width=width, height=height)
            y, page_blocks = MARGIN, []

        def place(kind, text, rect, block_html):
            nonlocal order
            spare, _ = page.insert_htmlbox(rect, block_html, css=css, archive=self.archive, scale_low=0.8)
            used = rect.height - spare if spare >= 0 else rect.height
            box = pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + used)
            spans = [s['bbox'] for b in page.get_text('dict', clip=box)['blocks'] for l in b.get('lines', [])
                     for s in l['spans'] if s['text'].strip()]
            if spans and kind != 'table':  # a table's box is its whole grid, not just the inked text
                box = pymupdf.Rect(min(s[0] for s in spans), min(s[1] for s in spans), max(s[2] for s in spans),
                                   max(s[3] for s in spans))
            plain = '\n'.join(' '.join(str(c) for c in row) for row in json.loads(text)) if kind == 'table' else text
            page_blocks.append({'id': f'b{order}', 'type': kind, 'order': order, 'text': plain,
                                'bbox': [round(box.x0 / width, 4), round(box.y0 / height, 4), round(box.x1 / width, 4),
                                         round(box.y1 / height, 4)]})
            order += 1
            return used

        new_page()
        footer = next((text for kind, text in blocks if kind == 'footer'), '')
        body = [(kind, text) for kind, text in blocks if kind != 'footer']
        columns = layout == 'multi_column'
        index = 0
        while index < len(body):
            kind, text = body[index]
            block_html = self.html(kind, text)
            two = columns and kind == 'paragraph'
            if two:  # flow consecutive paragraphs into two columns, right column first (RTL reading order)
                run = []
                while index < len(body) and body[index][0] == 'paragraph':
                    run.append(body[index][1])
                    index += 1
                column_width = (full - 20) / 2
                heights = [self.height(self.html('paragraph', t), column_width, css) + 6 for t in run]
                half, acc, split = sum(heights) / 2, 0.0, len(run)
                for i, h in enumerate(heights):
                    acc += h
                    if acc >= half:
                        split = i + 1
                        break
                for column, part in ((0, run[:split]), (1, run[split:])):
                    x1 = width - MARGIN - column * (column_width + 20)
                    cy = y
                    for t in part:
                        h = self.height(self.html('paragraph', t), column_width, css)
                        place('paragraph', t, pymupdf.Rect(x1 - column_width, cy, x1, cy + h + 4), self.html('paragraph', t))
                        cy += h + 6
                    column_bottom = cy
                    if column == 0:
                        right_bottom = column_bottom
                y = max(right_bottom, cy) + 6
                continue
            if kind == 'signature':
                h = self.height(block_html, full * 0.42, css)
                if y + h + 70 > height - MARGIN - 30:
                    new_page()
                x0 = MARGIN  # signatures sit on the left of an Arabic page
                place(kind, text, pymupdf.Rect(x0, y + 24, x0 + full * 0.42, y + 24 + h + 4), block_html)
                pen = page.new_shape()  # a hand-drawn looking signature stroke above the name
                sx, sy = x0 + 20 + rng.random() * 40, y + 14
                pen.draw_bezier((sx, sy), (sx + 30, sy - 18), (sx + 60, sy + 16), (sx + 110, sy - 6))
                pen.finish(color=(0.1, 0.1, 0.35), width=1.2)
                pen.commit()
                if rng.random() < 0.7:  # an ink stamp partly covering the signature block
                    cx, cy0, r = x0 + full * 0.42 + 40, y + 40, 34
                    shape = page.new_shape()
                    shape.draw_circle((cx, cy0), r)
                    shape.draw_circle((cx, cy0), r - 5)
                    shape.finish(color=(0.2, 0.25, 0.7), width=1.4)
                    shape.commit()
                    stamp_rect = pymupdf.Rect(cx - r + 6, cy0 - 10, cx + r - 6, cy0 + 12)
                    page.insert_htmlbox(stamp_rect, f'<div class="c" style="color:#3340b3;font-size:7pt">{html.escape(stamp_text)}</div>',
                                        css=css, archive=self.archive, scale_low=0.3)
                    page_blocks.append({'id': f'b{order}', 'type': 'stamp', 'order': order, 'text': stamp_text,
                                        'bbox': [round((cx - r) / width, 4), round((cy0 - r) / height, 4),
                                                 round((cx + r) / width, 4), round((cy0 + r) / height, 4)]})
                    order += 1
                y += h + 80
                index += 1
                continue
            h = self.height(block_html, full, css)
            if y + h > height - MARGIN - 30:
                new_page()
            place(kind, text, pymupdf.Rect(MARGIN, y, width - MARGIN, y + h + 4), block_html)
            y += h + (14 if kind in ('header', 'title') else 8)
            index += 1
        pages.append({'blocks': page_blocks})
        total = len(pages)
        for number, item in enumerate(pages, 1):  # footer and page number on every page
            target = doc[number - 1]
            line = f'{footer} - صفحة {arabic(number)} من {arabic(total)}'
            rect = pymupdf.Rect(MARGIN, height - MARGIN - 14, width - MARGIN, height - MARGIN + 6)
            target.insert_htmlbox(rect, self.html('footer', line), css=css.replace(f'{size}pt', '8pt'), archive=self.archive,
                                  scale_low=0.5)
            item['blocks'].append({'id': f'p{number}f', 'type': 'footer', 'order': 10_000, 'text': line,
                                   'bbox': [round(rect.x0 / width, 4), round(rect.y0 / height, 4),
                                            round(rect.x1 / width, 4), round(rect.y1 / height, 4)]})
        for item in pages:
            readable = [b for b in item['blocks'] if b['type'] != 'stamp']
            item['text'] = '\n'.join(b['text'] for b in sorted(readable, key=lambda b: b['order']))
        data = doc.tobytes(garbage=3, deflate=True)
        doc.close()
        return data, pages


# ---------------------------------------------------------------------------------------------- corpus
def scan(pdf: bytes, level: str, seed: int, dpi: int, image_format: str) -> tuple[bytes, str, list[dict]]:
    """Rasterize a born-digital PDF and apply the project's seeded degradation level to every page."""
    import pymupdf
    from PIL import Image
    from smartarchive.processing.degrade import degrade
    source = pymupdf.open(stream=pdf, filetype='pdf')
    images, params = [], []
    for number, page in enumerate(source):
        pix = page.get_pixmap(dpi=dpi)
        image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        result = degrade(image, level, seed + number)
        images.append(result.image)
        params.append(result.params)
    source.close()
    buffer = io.BytesIO()
    if len(images) == 1 and image_format in ('png', 'jpg'):
        images[0].save(buffer, format='PNG' if image_format == 'png' else 'JPEG', quality=90, dpi=(dpi, dpi))
        return buffer.getvalue(), image_format, params
    if image_format == 'tif':
        images[0].save(buffer, format='TIFF', save_all=True, append_images=images[1:], compression='tiff_lzw',
                       dpi=(dpi, dpi))
        return buffer.getvalue(), 'tif', params
    out = pymupdf.open()  # multi-page scans become image-only PDFs, like a scanner's output
    for image in images:
        page_buffer = io.BytesIO()
        image.save(page_buffer, format='JPEG', quality=85)
        page = out.new_page(width=A4[0], height=A4[1])
        page.insert_image(page.rect, stream=page_buffer.getvalue())
    data = out.tobytes(garbage=3, deflate=True)
    out.close()
    return data, 'pdf', params


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=ROOT / 'data' / 'synthetic' / 'corpus_v1')
    parser.add_argument('--documents', type=int, default=150)
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--scanned', type=float, default=0.6, help='share of documents delivered as degraded scans')
    parser.add_argument('--dpi', type=int, default=200)
    parser.add_argument('--fonts', type=Path, default=Path(r'C:\Windows\Fonts'))
    args = parser.parse_args(argv)
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error(f'{out} is not empty; choose a new folder (corpora are never overwritten)')
    rng = random.Random(args.seed)
    renderer = Renderer(args.fonts)
    (out / 'archive').mkdir(parents=True)
    (out / 'ground_truth').mkdir()
    manifest, documents = [], []
    kinds = list(TYPES)
    plan = [kinds[i % len(kinds)] for i in range(args.documents)]
    rng.shuffle(plan)
    levels = ['clean', 'mild', 'medium', 'severe']
    for index, kind in enumerate(plan, 1):
        group, departments, layouts = TYPES[kind]
        department = DEPARTMENTS[rng.choice(departments)]
        day = date(2023, 1, 1) + timedelta(days=rng.randint(0, 1360))
        prefix = {'incoming_letter': 'و', 'outgoing_letter': 'ص', 'decision': 'ق', 'admin_form': 'ن', 'minutes': 'م',
                  'contract': 'ع', 'invoice': 'INV-', 'report': 'ت'}[kind]
        serial = rng.randint(1, 999)
        number = f'{prefix}{serial}-{day.year}' if kind == 'invoice' else f'{prefix}/{arabic(serial)}/{arabic(day.year)}'
        doc_id = f'S{index:04d}'
        documents.append({'doc_id': doc_id, 'kind': kind, 'group': group, 'department': department, 'day': day,
                          'number': number, 'layout': rng.choice(layouts), 'seed': rng.randint(0, 10 ** 9),
                          'relations': []})
    # relations: ~6% exact copies (filed again elsewhere), ~6% near duplicates, ~6% versions (same number)
    extra = []
    for base in rng.sample(documents, max(1, len(documents) // 6)):
        relation = rng.choice(['exact_duplicate', 'near_duplicate', 'version_of'])
        copy = dict(base, doc_id=f'S{len(documents) + len(extra) + 1:04d}', relations=[{'kind': relation, 'target': base['doc_id']}])
        if relation == 'exact_duplicate':
            copy['department'] = DEPARTMENTS[rng.choice(list(DEPARTMENTS))]
        elif relation == 'version_of':
            copy['seed'] = rng.randint(0, 10 ** 9)  # new body text, same type, number and date
            copy['day'] = base['day'] + timedelta(days=rng.randint(3, 40))
        extra.append(copy)
    documents += extra
    rendered: dict[str, tuple[bytes, list, dict]] = {}
    files: dict[str, tuple[bytes, str, str, list]] = {}
    queries = []
    for item in documents:
        local = random.Random(item['seed'])
        kinds_of = {r['kind']: r['target'] for r in item['relations']}
        if 'exact_duplicate' in kinds_of:  # the very same file, stored again (e.g. filed in two departments)
            pdf, pages, truth = rendered[kinds_of['exact_duplicate']]
            data, extension, level, degradation = files[kinds_of['exact_duplicate']]
        else:
            if 'near_duplicate' in kinds_of:  # same text, rendered again (other font/size) and maybe scanned
                truth = json.loads(json.dumps(rendered[kinds_of['near_duplicate']][2]))
            else:
                truth = content(item['kind'], local, item['number'], item['day'], item['department'])
            pdf, pages = renderer.render([tuple(b) for b in truth['blocks']], item['layout'], local,
                                         OWN.replace('مديرية ', ''))
            scanned = local.random() < args.scanned
            level = levels[local.randrange(4)] if scanned else 'born_digital'
            data, extension, degradation = (scan(pdf, level, item['seed'], args.dpi,
                                                 local.choice(['png', 'jpg', 'tif', 'pdf']))
                                            if scanned else (pdf, 'pdf', []))
        rendered[item['doc_id']] = (pdf, pages, truth)
        files[item['doc_id']] = (data, extension, level, degradation)
        descriptive = local.random() < 0.2
        name = (f"{truth['metadata']['subject'][:40].replace('/', '-')}.{extension}" if descriptive and truth['metadata']['subject']
                else f'scan_{item["doc_id"][1:]}.{extension}')
        folder = out / 'archive' / item['department'] / str(item['day'].year)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        if path.exists():
            path = folder / f'{path.stem}_{item["doc_id"]}{path.suffix}'
        path.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        entry = {'doc_id': item['doc_id'], 'file': path.relative_to(out).as_posix(), 'sha256': sha,
                 'type': item['kind'], 'group': item['group'], 'folder': f"{item['department']}/{item['day'].year}",
                 'layout': item['layout'], 'quality': level, 'pages': len(pages), 'relations': item['relations'],
                 'descriptive_filename': descriptive}
        manifest.append(entry)
        truth_doc = {**entry, 'synthetic': True, 'generator': GENERATOR, 'metadata': truth['metadata'],
                     'degradation': degradation,
                     'pages': [{'page_no': n, 'width_pt': A4[0], 'height_pt': A4[1], **p} for n, p in enumerate(pages, 1)]}
        (out / 'ground_truth' / f"{item['doc_id']}.json").write_text(json.dumps(truth_doc, ensure_ascii=False, indent=1),
                                                                   encoding='utf-8')
        meta = truth['metadata']
        if not item['relations'] and meta['subject'] and local.random() < 0.6:
            queries.append({'query': meta['subject'], 'kind': 'subject', 'relevant': [item['doc_id']], 'page': 1})
        if not item['relations'] and local.random() < 0.25:
            queries.append({'query': meta['reference_number'], 'kind': 'reference_number', 'relevant': [item['doc_id']], 'page': 1})
        print(f"{item['doc_id']} {item['kind']:<16} {item['layout']:<12} {level:<12} {len(pages)}p  {entry['file']}")
    for query in queries:  # versions and copies of a relevant document are relevant too
        for entry in manifest:
            if any(r['target'] in query['relevant'] for r in entry['relations']):
                query['relevant'].append(entry['doc_id'])
    for number, query in enumerate(queries, 1):
        query['id'] = f'Q{number:03d}'
    (out / 'queries.json').write_text(json.dumps(queries, ensure_ascii=False, indent=1), encoding='utf-8')
    (out / 'manifest.json').write_text(json.dumps({'generator': GENERATOR, 'seed': args.seed, 'documents': manifest},
                                                  ensure_ascii=False, indent=1), encoding='utf-8')
    pages_total = sum(entry['pages'] for entry in manifest)
    (out / 'README.md').write_text(
        f'# Synthetic corpus ({GENERATOR}, seed {args.seed})\n\n'
        f'{len(manifest)} files, {pages_total} pages, 8 document types, fictional organizations, people, numbers and '
        f'dates. Generated by `tools/synth_corpus.py`; {args.scanned:.0%} delivered as scans degraded with '
        f'`smartarchive.processing.degrade` (clean/mild/medium/severe). Ground truth (text in reading order, block '
        f'boxes, metadata, relations) is exact because the documents were rendered from it.\n\n'
        f'Report every result on this corpus as synthetic. Import with:\n\n'
        f'    tools\\import_tree.py "{out / "archive"}" --into "مجموعة اصطناعية v1"\n', encoding='utf-8')
    print(f'\n{len(manifest)} files, {pages_total} pages, {len(queries)} queries -> {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
