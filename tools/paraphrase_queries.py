r"""Paraphrased search queries: the same information need as a subject query, in other words.

  .\.venv\Scripts\python.exe tools/paraphrase_queries.py data\synthetic\corpus_v1

Each subject query in queries.json whose wording follows a known pattern gets a rewrite. The document type's
own words are replaced by synonyms a person might type instead («محضر اجتماع» → «وقائع جلسة»,
«فاتورة» → «مطالبة مالية»). Names of projects, companies and people are kept, since a person searching
remembers them. The result, queries_paraphrase.json with kind `paraphrase` and the same relevant documents,
measures what dense retrieval is for (ADR 0013). The rewrite rules are fixed here and were not tuned on search
results.
"""
import json
from pathlib import Path
import re
import sys

# (pattern on the subject, rewrite). The first matching rule wins; \1 is the kept name.
RULES = [
    (r'^محضر اجتماع لجنة متابعة مشروع (.+)$', r'وقائع جلسة الفريق المشرف على \1'),
    (r'^فاتورة (?:شركة|مؤسسة|مكتب) (.+)$', r'مطالبة مالية من \1'),
    (r'^تقرير فني حول سير العمل في مشروع (.+)$', r'مستوى التقدم في تنفيذ \1'),
    (r'^تقرير فني حول نتائج الكشف على مشروع (.+)$', r'نتائج المعاينة الهندسية ل\1'),
    (r'^تقرير فني حول تقييم أداء مشروع (.+)$', r'مراجعة إنجاز \1'),
    (r'^عقد تقديم خدمات لمشروع (.+)$', r'اتفاقية خدمات \1'),
    (r'^عقد تنفيذ أعمال لمشروع (.+)$', r'اتفاقية مقاولة \1'),
    (r'^عقد توريد لمشروع (.+)$', r'اتفاقية شراء مواد ل\1'),
    (r'^طلب تزويدنا ببيانات مشروع (.+)$', r'نرجو إرسال معلومات عن \1'),
    (r'^تشكيل لجنة لمتابعة مشروع (.+)$', r'إنشاء فريق للإشراف على \1'),
    (r'^اعتماد الجدول الزمني لمشروع (.+)$', r'إقرار خطة المواعيد ل\1'),
    (r'^تمديد مدة مشروع (.+)$', r'إطالة فترة تنفيذ \1'),
    (r'^الموافقة على صرف مستحقات (?:شركة|مؤسسة|مكتب) (.+)$', r'إقرار دفع المبالغ المستحقة ل\1'),
    (r'^عقد اجتماع تنسيقي بخصوص (.+)$', r'دعوة إلى لقاء تنسيق حول \1'),
    (r'^تسمية ممثل عن الدائرة في لجنة (.+)$', r'ترشيح مندوب للمشاركة في لجنة \1'),
    (r'^تكليف السيد (.+?) بمهام رئيس قسم$', r'إسناد رئاسة القسم إلى \1'),
    (r'^منح إجازة إدارية للعاملين في (.+)$', r'عطلة رسمية لموظفي \1'),
    (r'^استمارة تحديث بيانات موظف$', 'نموذج تعديل معلومات العامل'),
    (r'^نموذج طلب صرف مستلزمات$', 'استمارة طلب أدوات مكتبية'),
    (r'^نموذج طلب إجازة$', 'استمارة طلب عطلة'),
]


def rewrite(subject: str) -> str | None:
    for pattern, replacement in RULES:
        if re.match(pattern, subject):
            return re.sub(r'(^|\s)لال', r'\1لل', re.sub(pattern, replacement, subject))  # ل + ال → لل
    return None


def main(argv=None) -> int:
    corpus = Path((argv or sys.argv[1:])[0])
    queries = json.loads((corpus / 'queries.json').read_text(encoding='utf-8'))
    out = []
    for query in queries:
        if query['kind'] != 'subject':
            continue
        text = rewrite(query['query'])
        if text:
            out.append({**query, 'id': 'P' + query['id'][1:], 'kind': 'paraphrase', 'query': text,
                        'source_query': query['query']})
    (corpus / 'queries_paraphrase.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{len(out)} paraphrased queries from {sum(q["kind"] == "subject" for q in queries)} subject queries')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
