"""Explainable keyword classifier for Arabic institutional documents (baseline, `keywords-v1`).

Each category has keywords. A keyword matches a whole word, optionally preceded by Arabic clitics
(و ف ب ك ل ال وال بال لل ...), so "قرار" matches "والقرار" but not "استقرار". Text is compared in the
normalized form used by search (see search/arabic.py).

Score of a category = sum over its keyword hits of
    1 per occurrence (at most 3 per keyword, so one repeated word cannot dominate)
  + 1 extra if the keyword appears in the document heading (first 300 normalized characters)
  + 3 if the keyword appears in the file name (people name scans after what they are).
Confidence = top / (top + runner_up + 1): high only when one category clearly leads.
The classifier abstains (no category) when the top score (default 3) or confidence (default 0.5) is
below the thresholds: a single keyword, even in the heading, is not enough.
It only suggests; a person confirms or changes every classification.
"""
from dataclasses import dataclass, field
import re

from smartarchive.search.arabic import normalize

METHOD = 'keywords-v1'
HEAD_CHARS = 300
MAX_PER_KEYWORD = 3
_CLITICS = r'(?:و|ف)?(?:ب|ك|ل)?(?:ال|ل)?'


@dataclass
class Category:
    id: str
    name: str
    keywords: list[str]


@dataclass
class Result:
    category_id: str | None
    confidence: float | None
    scores: dict[str, float]
    evidence: dict[str, list[dict]] = field(default_factory=dict)
    reason: str = ''

    @property
    def candidates(self) -> list[tuple[str, float]]:
        return sorted(((k, v) for k, v in self.scores.items() if v > 0), key=lambda item: -item[1])


def _pattern(keyword: str) -> re.Pattern | None:
    words = normalize(keyword).split()
    if not words:
        return None
    body = r'\s+'.join(re.escape(word) for word in words)
    return re.compile(rf'(?:^|\s){_CLITICS}{body}(?=\s|$)')


def classify(text: str, filename: str, categories: list[Category],
             min_score: float = 3.0, min_confidence: float = 0.5) -> Result:
    normalized = normalize(text)
    head = normalized[:HEAD_CHARS]
    name = normalize(filename.rsplit('.', 1)[0])
    scores: dict[str, float] = {}
    evidence: dict[str, list[dict]] = {}
    for category in categories:
        total, hits = 0.0, []
        for keyword in category.keywords:
            pattern = _pattern(keyword)
            if pattern is None:
                continue
            count = len(pattern.findall(normalized))
            in_head = bool(pattern.search(head))
            in_name = bool(pattern.search(name))
            if not (count or in_name):
                continue
            points = min(count, MAX_PER_KEYWORD) + (1 if in_head else 0) + (3 if in_name else 0)
            total += points
            hits.append({'keyword': keyword, 'count': count, 'heading': in_head, 'filename': in_name,
                         'points': points})
        scores[category.id] = total
        if hits:
            evidence[category.id] = sorted(hits, key=lambda hit: -hit['points'])
    ranked = sorted(scores.values(), reverse=True) + [0.0, 0.0]
    top, second = ranked[0], ranked[1]
    if top <= 0:
        return Result(None, None, scores, evidence, 'no_keywords' if normalized or name else 'no_text')
    confidence = round(top / (top + second + 1), 4)
    best = max(scores, key=lambda key: scores[key])
    if top < min_score:
        return Result(None, confidence, scores, evidence, 'weak_evidence')
    if confidence < min_confidence:
        return Result(None, confidence, scores, evidence, 'ambiguous')
    return Result(best, confidence, scores, evidence, 'suggested')


DEFAULT_CATEGORIES = [
    ('decision', 'قرار إداري', 'قرارات وأوامر إدارية صادرة عن جهة مختصة',
     ['قرار', 'يقرر', 'تقرر', 'قررنا', 'المادة', 'يعمل به', 'يبلغ', 'بناء على', 'استنادا', 'صلاحيات', 'المصادقة']),
    ('circular', 'تعميم', 'تعاميم وتوجيهات موجهة لعدد من الجهات أو الموظفين',
     ['تعميم', 'يعمم', 'نعمم', 'جميع الموظفين', 'كافة', 'للاطلاع', 'التقيد', 'الالتزام بما ورد', 'العاملين']),
    ('letter', 'مراسلة رسمية', 'كتب ومراسلات صادرة أو واردة',
     ['المحترم', 'تحية طيبة', 'وبعد', 'نرجو', 'يرجى', 'نحيطكم', 'الموضوع', 'المرفق', 'مع الشكر', 'كتابكم', 'الاحترام']),
    ('minutes', 'محضر اجتماع', 'محاضر الاجتماعات واللجان',
     ['محضر', 'اجتماع', 'الحضور', 'جدول الاعمال', 'المجتمعون', 'انعقد', 'الجلسة', 'اللجنة', 'رئيس اللجنة', 'تقرر']),
    ('report', 'تقرير', 'تقارير دورية أو فنية أو إحصائية',
     ['تقرير', 'ملخص', 'النتائج', 'التوصيات', 'خلال الفترة', 'احصائيات', 'نسبة', 'الانجاز', 'التحليل']),
    ('contract', 'عقد أو اتفاقية', 'عقود واتفاقيات ومذكرات تفاهم',
     ['عقد', 'اتفاقية', 'الطرف الاول', 'الطرف الثاني', 'الطرفين', 'بنود', 'يلتزم', 'مدة العقد', 'مذكرة تفاهم', 'التزامات']),
    ('financial', 'مستند مالي', 'فواتير وسندات صرف وقبض وكشوف مالية',
     ['فاتورة', 'المبلغ', 'المجموع', 'ضريبة', 'دينار', 'ريال', 'دولار', 'سند صرف', 'سند قبض', 'الرصيد', 'الموازنة', 'شيك']),
    ('certificate', 'شهادة', 'شهادات وإفادات رسمية',
     ['شهادة', 'يشهد', 'نشهد', 'نفيد', 'افادة', 'لمن يهمه الامر', 'حصل على', 'بتقدير', 'منحت']),
    ('request', 'طلب', 'طلبات واستدعاءات مقدمة من أفراد أو جهات',
     ['طلب', 'مقدم الطلب', 'ارجو الموافقة', 'استدعاء', 'التماس', 'الموافقة على', 'اتقدم', 'راجيا']),
    ('personnel', 'شؤون الموظفين', 'تعيين ونقل وإجازات وترقيات ورواتب الموظفين',
     ['اجازة', 'تعيين', 'نقل', 'ترقية', 'الموظف', 'الرقم الوظيفي', 'راتب', 'الدرجة الوظيفية', 'مباشرة العمل', 'استقالة']),
]
