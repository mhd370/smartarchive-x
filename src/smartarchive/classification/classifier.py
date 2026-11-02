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

Hierarchy: each type belongs to a level-1 group (administrative, financial, legal, technical). Group scores
are the sums of their types' scores, so a document can be confidently "financial" while its type is unclear;
the result then names the group and leaves the type to a person (reason `group_only`).
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
    group_id: str | None = None


@dataclass
class Result:
    category_id: str | None
    confidence: float | None
    scores: dict[str, float]
    evidence: dict[str, list[dict]] = field(default_factory=dict)
    reason: str = ''
    group_id: str | None = None
    group_confidence: float | None = None
    group_scores: dict[str, float] = field(default_factory=dict)

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
    # Level 1 (group): the evidence of all its types together. A clear group with an unclear type is
    # reported as such (e.g. financial -> uncertain subtype -> human review), as the hierarchy intends.
    groups: dict[str, float] = {}
    for category in categories:
        if category.group_id:
            groups[category.group_id] = groups.get(category.group_id, 0.0) + scores[category.id]
    group_id, group_confidence = _leader(groups, min_score, min_confidence)
    ranked = sorted(scores.values(), reverse=True) + [0.0, 0.0]
    top, second = ranked[0], ranked[1]
    extra = {'group_id': group_id, 'group_confidence': group_confidence, 'group_scores': groups}
    if top <= 0:
        return Result(None, None, scores, evidence, 'no_keywords' if normalized or name else 'no_text', **extra)
    confidence = round(top / (top + second + 1), 4)
    best = max(scores, key=lambda key: scores[key])
    if top < min_score:
        return Result(None, confidence, scores, evidence, 'weak_evidence', **extra)
    if confidence < min_confidence:
        return Result(None, confidence, scores, evidence, 'group_only' if group_id else 'ambiguous', **extra)
    owner = next((c.group_id for c in categories if c.id == best), None)
    if owner:  # the chosen type always belongs to the reported group
        rivals = max((value for key, value in groups.items() if key != owner), default=0.0)
        extra.update(group_id=owner, group_confidence=round(groups[owner] / (groups[owner] + rivals + 1), 4))
    return Result(best, confidence, scores, evidence, 'suggested', **extra)


def _leader(scores: dict[str, float], min_score: float, min_confidence: float) -> tuple[str | None, float | None]:
    ranked = sorted(scores.items(), key=lambda item: -item[1]) + [(None, 0.0), (None, 0.0)]
    (best, top), (_, second) = ranked[0], ranked[1]
    if not best or top < min_score:
        return None, None
    confidence = round(top / (top + second + 1), 4)
    return (best, confidence) if confidence >= min_confidence else (None, confidence)


GROUPS = [('administrative', 'إداري'), ('financial', 'مالي'), ('legal', 'قانوني'), ('technical', 'فني')]

# The eight document types proposed in the project brief, under four level-1 groups.
DEFAULT_CATEGORIES = [
    ('incoming_letter', 'مراسلة واردة', 'administrative', 'كتب ومراسلات واردة إلى المؤسسة من جهات أخرى',
     ['وارد', 'رقم الوارد', 'تاريخ الورود', 'كتابكم رقم', 'اشارة الى كتابكم', 'ردا على كتابكم', 'ورد الينا',
      'الجهة المرسلة', 'تحية طيبة وبعد']),
    ('outgoing_letter', 'مراسلة صادرة', 'administrative', 'كتب ومراسلات صادرة من المؤسسة إلى جهات أخرى',
     ['صادر', 'رقم الصادر', 'نحيطكم علما', 'نرجو التكرم', 'يرجى التكرم', 'نفيدكم', 'تفضلوا بقبول فائق الاحترام',
      'المحترم', 'مع الشكر']),
    ('decision', 'قرار إداري', 'administrative', 'قرارات وأوامر إدارية صادرة عن جهة مختصة',
     ['قرار', 'يقرر', 'تقرر', 'قررنا', 'المادة', 'يعمل به', 'يبلغ', 'بناء على', 'استنادا', 'صلاحيات', 'المصادقة']),
    ('admin_form', 'نموذج إداري', 'administrative', 'نماذج واستمارات وطلبات إدارية معبأة',
     ['نموذج', 'استمارة', 'طلب', 'الاسم الكامل', 'الرقم الوظيفي', 'توقيع مقدم الطلب', 'يعبأ من قبل', 'اسم الموظف',
      'القسم', 'خاص بالادارة']),
    ('minutes', 'محضر اجتماع', 'administrative', 'محاضر الاجتماعات واللجان',
     ['محضر', 'اجتماع', 'الحضور', 'جدول الاعمال', 'المجتمعون', 'انعقد', 'الجلسة', 'اللجنة', 'رئيس اللجنة', 'تقرر']),
    ('contract', 'عقد أو اتفاقية', 'legal', 'عقود واتفاقيات ومذكرات تفاهم',
     ['عقد', 'اتفاقية', 'الطرف الاول', 'الطرف الثاني', 'الطرفين', 'بنود', 'يلتزم', 'مدة العقد', 'مذكرة تفاهم', 'التزامات']),
    ('invoice', 'فاتورة', 'financial', 'فواتير ومطالبات مالية',
     ['فاتورة', 'رقم الفاتورة', 'المبلغ', 'المجموع', 'الاجمالي', 'ضريبة', 'الكمية', 'سعر الوحدة', 'دينار', 'ريال',
      'دولار', 'المورد']),
    ('report', 'تقرير فني', 'technical', 'تقارير فنية ودورية وإحصائية',
     ['تقرير', 'ملخص', 'النتائج', 'التوصيات', 'المنهجية', 'خلال الفترة', 'احصائيات', 'نسبة', 'الانجاز', 'التحليل']),
]
TAXONOMY_VERSION = 'brief-v1'
