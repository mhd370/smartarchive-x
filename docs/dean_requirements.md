# متطلبات العميد ومتابعة تنفيذها / Dean's requirements and traceability

هذا الملف هو المرجع الثابت لما يجب أن يصل إليه المشروع. النص الأصلي لرسالة العميد في آخر الملف دون تعديل.
This file is the fixed reference for the project's target. The dean's original message is reproduced verbatim at the end.

الحالة / Status: ✅ منفذ · 🟡 جزئي · ❌ لم يبدأ — آخر تحديث: v0.17.0 (Sprint 12)

## 2. الهدف النهائي — الموقع

| المتطلب | الحالة | أين / ملاحظات |
|---|---|---|
| رفع ملفات PDF والصور | ✅ | `/upload`، `tools/import_tree.py` للاستيراد الجماعي |
| الاحتفاظ بالأصل دون تعديل | ✅ | SHA-256، إنشاء حصري، فحص عند كل تنزيل، نسخ احتياطي موثق |
| فحص جودة كل صفحة | ✅ | Q = w·[B,C,R,S,L] لكل صفحة (`processing/quality.py`) |
| تصحيح الميل والاتجاه والضوضاء | ✅ | OSD للاتجاه، Deskew، إزالة ضوضاء مشروطة، دون Binarization |
| اكتشاف مناطق النص والجداول والصور والعناوين | 🟡 | `layout-v1` (ADR 0012): الجداول المسطّرة تُقرأ خلية خلية من اليمين، والعمودان بترتيب صحيح؛ خطأ الجداول على الاختبار من 40.7% إلى 33.3%؛ الصور والعناوين كمناطق منفصلة لاحقًا |
| اختيار محرك OCR الأنسب تلقائيًا | 🟡 | المسار يُحسب لكل صفحة؛ Tesseract بنموذجين مقاسين؛ PaddleOCR وEasyOCR قورنا على 40 صفحة: أسوأ إجمالًا (40.9% و43.2% مقابل 30.8%) وأبطأ 7–40 مرة، فبقي Tesseract |
| استخراج النص العربي والإنجليزي | ✅ | ara+eng |
| حفظ إحداثيات النص | ✅ | صناديق الأسطر والكلمات مُعادة إلى إحداثيات الأصل |
| استخراج التاريخ ورقم الكتاب والمرسل والموضوع | ✅ | `rules-v2` + تصحيح بشري؛ دقته مقاسة لكل حقل على Ground Truth (Sprint 6) |
| تصنيف الوثيقة والمجلد المناسب | ✅ | 8 أنواع تحت 4 مجموعات؛ مصنّف متعلّم `tfidf-svm-v1` (اختبار مستقل: دقة 81.2%، صحة الإجابات 98.0%، Macro-F1 88.8%)؛ دمج مع صورة الصفحة `visual-layout-v1` يرفع الدقة إلى 89.6% وMacro-F1 إلى 92.3% (ADR 0015)؛ اقتراح المجلد `folder-knn-v1` من أشبه 5 وثائق محفوظة: صحيح أولًا 58.6%، وضمن الثلاثة المعروضة 81.5% |
| كشف الوثائق المتكررة والنسخ المختلفة | ✅ | SHA-256، MinHash للنص، نسخ بنفس الرقم/الموضوع (Sprint 5) |
| إنشاء فهرس حرفي ودلالي | ✅ | فهرس حرفي: المطابقة الكاملة + BM25 على الجذوع الخفيفة مدموجة بـRRF (`hybrid-rrf-v3`)؛ فهرس المقاطع الثلاثية مبني لكنه اختياري بعد أن أظهر الـ Ablation أنه يخفض الاستدعاء (ADR 0014)؛ فهرس دلالي `dense-e5-small-v1` منفذ ومقاس (ADR 0013): +6.7 نقطة على التطوير و+0.5 فقط على الاختبار، فهو اختياري ومعطّل افتراضيًا |
| البحث بالكلمات أو باللغة الطبيعية | 🟡 | بحث مرتّب حسب الصلة لا يشترط كل الكلمات (اختبار: Recall@10 58.1% مقابل 46.2% للحرفي، أرقام الكتب 40.8% مقابل 8.0%)؛ الاستعلامات المعاد صياغتها بكلمات أخرى تُوجد بنسبة الثلث تقريبًا، والبحث الدلالي لم يحسّنها على الاختبار |
| إعادة ترتيب النتائج بالذكاء الاصطناعي | ✅ | Cross-Encoder متعدد اللغات (mMiniLM مدرّب على mMARCO، ONNX على المعالج) يعيد ترتيب أول 20 نتيجة، بطريقتين `replace` و`fuse` (ADR 0014)؛ اختياري (`SMARTARCHIVE_RERANK=1`) ومقاس على التطوير ثم الاختبار في docs/synthetic_evaluation.md |
| إعادة التصنيف عند ظهور أدلة أقوى | ✅ | `reclass-delta-v1` (ADR 0011): دليل جديد يخالف التصنيف المعتمد بحصة ≥ 0.6 وفرق Δ ≥ 0.3 يصبح اقتراحًا؛ لا تغيير إلا بقرار مراجع (قبول بسبب أو رفض مسجّل)؛ العتبات مختارة على مجموعة التطوير: التقاط 76.7% من التصنيفات الخاطئة مع إنذار خاطئ 0.2% |
| عرض الملف والصفحة والمقطع الداعم | ✅ | نتيجة البحث تفتح الصفحة المطابقة وتظلّل على صورتها الأسطر التي تحوي كلمات البحث، مع المقطع المُبرز في النتائج |
| تحويل الصفحات ضعيفة الثقة للمراجعة | ✅ | `/review` |
| تسجيل كل تعديل بهوية المستخدم ووقته | ✅ | سجلات append-only |

## 33. الحد الأدنى القابل للتسليم

| البند | الحالة |
|---|---|
| مراجعة 35–50 ورقة وجدول مقارنة | ✅ 51 مرجعًا في 9 محاور، كلها مدققة على الناشر أو فهرس، مع جدول مقارنة وتحديد الفجوة (`docs/literature_review.md`) |
| 500 صفحة، 100 صفحة Ground Truth، 5 أنواع | ✅ (اصطناعية موثقة، ADR 0008) تطوير `corpus_v1` 499 صفحة + اختبار مستقل `corpus_v2` 624 صفحة، Ground Truth كامل لكل صفحة، 8 أنواع؛ Arabic Documents OCR Dataset وKITAB-Bench للتحقق الخارجي |
| حفظ أصل وبصمة SHA-256 | ✅ |
| 3 مسارات OCR، تحليل تخطيط، نص خام ومصحح | 🟡 مسار واحد + تسوية الإضاءة + تحليل التخطيط `layout-v1`؛ النص المصحح بشريًا موجود؛ محركان آخران قورنا ولم يتفوقا |
| 3 Baselines للتصنيف + نموذج متعدد الوسائط | ✅ ثلاثة خطوط أساس مقاسة بالدقة والتغطية وMacro-F1 (79.6% / 88.8% / 87.1%)؛ نموذج متعدد الوسائط نص + تخطيط الصورة (ADR 0015): دقة 89.6%، والمسوحات الشديدة من 1.1% إلى 46.2%؛ مقاس خارج الخدمة ولم يُربط بعد بالاقتراح الآلي |
| BM25، Dense، Cross-Encoder، فهرس واعٍ بالثقة | ✅ الأربعة منفذة ومقاسة (ADR 0013، 0014): BM25 هو الافتراضي مع المطابقة الكاملة؛ Dense والفهرس الواعي بالثقة لم يتفوقا على الاختبار فبقيا اختياريين ومعطلين؛ Cross-Encoder اختياري |
| Folder Knowledge Graph مبسط | ✅ «خريطة الأرشيف» `folder-graph-v1`: المجلدات وأنواع وثائقها (مؤكد/مقترح) والعلاقات العابرة للمجلدات، `/api/graph` |
| Reclassification Engine | ✅ `reclass-delta-v1` مع قائمة مراجعة وسجل رفض append-only (ADR 0011) |
| 50 استعلامًا مقيمًا، Ablation، CER/WER/Macro-F1/NDCG | ✅ 321 استعلامًا (تطوير) و430 (اختبار) + 239/311 معاد صياغتها؛ CER/WER وMacro-F1 وRecall/MRR/nDCG@10 مقاسة؛ Ablation للقراءة الضوئية (الإضاءة، النموذج، الدقة، التخطيط) وللبحث (كل تركيبات الترتيبات السبعة): حرفي + BM25 أفضل من الدمج الثلاثي فصار الافتراضي (اختبار Recall@10 من 54.9% إلى 58.1%، أرقام الكتب من 29.8% إلى 40.8%) |
| واجهة عربية RTL، عرض الصفحة والدليل، صلاحيات وتدقيق، مستودع منظم | ✅ |
| مسودة ورقة بالإنجليزية | ✅ مسودة كاملة (مقدمة، أدبيات، نظام، طرق، إعداد، نتائج، نقاش، 44 مرجعًا) في Claude Docs |

---

## النص الأصلي لرسالة العميد

الفكرة ممتازة لمشروع سنة خامسة، لأنها لا تقتصر على تحويل الصور إلى نص، بل تبني موقع أرشفة مؤسساتي كامل يبدأ من رفع الوثيقة وينتهي بتصنيفها وفهرستها والبحث الذكي داخلها وإعادة تصنيفها عند اكتشاف معلومات جديدة. وبسبب مدة التنفيذ القصيرة، الأفضل بناء نموذج أولي على 500 إلى 2,000 صفحة عربية و5 إلى 8 أنواع وثائق، بدل محاولة رقمنة أرشيف كامل.

1. العنوان المقترح
بالعربية

تصميم وتنفيذ منصة ذكية للأرشفة الآلية للوثائق العربية باستخدام OCR واعٍ بالجودة والتصنيف متعدد الوسائط والفهرسة الهجينة

بالإنجليزية

SmartArchive-X: A Quality-Aware OCR, Multimodal Classification, and Hybrid Indexing Platform for Intelligent Arabic Document Archiving

عنوان مناسب للورقة العلمية

SmartArchive-X: Confidence-Aware OCR Routing and Adaptive Hybrid Indexing for Arabic Institutional Archives

2. الهدف النهائي للمشروع

يكون النظام موقعًا إلكترونيًا يسمح بما يلي:

رفع ملفات PDF والصور.
الاحتفاظ بالملف الأصلي دون تعديل.
فحص جودة كل صفحة.
تصحيح الميل والاتجاه والضوضاء.
اكتشاف مناطق النص والجداول والصور والعناوين.
اختيار محرك OCR الأنسب تلقائيًا.
استخراج النص العربي والإنجليزي.
حفظ إحداثيات النص داخل الصفحة.
استخراج التاريخ ورقم الكتاب والمرسل والموضوع.
تصنيف الوثيقة والمجلد المناسب.
كشف الوثائق المتكررة والنسخ المختلفة.
إنشاء فهرس حرفي ودلالي.
البحث بالكلمات أو باللغة الطبيعية.
إعادة ترتيب النتائج بالذكاء الاصطناعي.
إعادة تصنيف الوثيقة إذا ظهرت أدلة أقوى.
عرض الملف والصفحة والمقطع الذي دعم النتيجة.
تحويل الصفحات ضعيفة الثقة إلى موظف للمراجعة.
تسجيل كل تعديل مع هوية المستخدم ووقته.
3. نطاق المشروع خلال شهر ونصف
حجم النموذج الأولي

أوصي بالنطاق التالي:

500 إلى 2,000 صفحة.
5 إلى 8 أنواع وثائق.
100 إلى 200 صفحة مفرغة يدويًا لقياس OCR.
50 إلى 100 استعلام بحث مقيم يدويًا.
العربية لغة أساسية.
الإنجليزية لغة مساعدة.
PDF وJPG وPNG وTIFF.
3 مستويات لجودة الوثائق.
3 أنواع تخطيط: بسيط، متعدد الأعمدة، وجدولي.
أنواع الوثائق المقترحة
مراسلات واردة
مراسلات صادرة
قرارات إدارية
عقود
فواتير
محاضر اجتماعات
تقارير فنية
نماذج إدارية

4. الفجوة البحثية

النظام التقليدي يعمل عادة بهذه الطريقة:

PDF → OCR واحد → Text → Vector Database → Search


المشكلة أن خطأ OCR أو ترتيب القراءة ينتقل مباشرة إلى الفهرس. مسح وثيقة بدقة حروف مرتفعة لا يكفي إذا اختلطت أعمدة الصفحة أو ضاعت رؤوس الجداول؛ فمراجعة ACL 2026 أوضحت أن أنظمة OCR النصية تفقد أحيانًا التفاصيل الهيكلية، بينما تواجه الأنظمة متعددة الوسائط صعوبات في السياق والكلفة والوثائق الكبيرة.

الفجوة التي يعالجها المشروع هي:

اختيار OCR حسب جودة الصفحة ونوعها.
الحفاظ على ترتيب القراءة والتخطيط.
عدم تصحيح النص إلا عند توفر ثقة كافية.
استخدام الصورة والنص والتخطيط في التصنيف.
الجمع بين البحث الحرفي والدلالي والبصري.
إدخال ثقة OCR في ترتيب النتائج.
استخدام بنية المجلد والبيانات الوصفية كدليل.
إعادة التصنيف بصورة مضبوطة، لا تعديل الملف تلقائيًا.
الإجابة مع استشهاد بالملف والصفحة.
الامتناع عن الإجابة عند ضعف الأدلة.
5. المرحلة الأولى: تجميع الأوراق والخوارزميات
مدة المرحلة

خمسة أيام.

الفترة
يناير 2022 – 24 أكتوبر 2026


مع التركيز على أبحاث 2025 و2026، والرجوع إلى الأبحاث الأقدم للخوارزميات ومجموعات البيانات الأساسية.

قواعد البيانات
Scopus.
IEEE Xplore.
ACM Digital Library.
ACL Anthology.
SpringerLink.
ScienceDirect.
arXiv.
Hugging Face.
Google Scholar للوصول إلى نسخ المؤلفين المجانية.

توفر Scopus بحثًا متقدمًا ومرشحات للوثائق والمؤلفين والمؤسسات والموضوعات، وتذكر الصفحة الرسمية أن بياناتها تُحدَّث يوميًا.

كلمات البحث
Arabic OCR document understanding 2026
quality-aware OCR routing
historical document OCR post-correction
document layout analysis transformer
Arabic document classification
multimodal document retrieval
hybrid BM25 dense retrieval
visual document retrieval
confidence-aware information retrieval
document indexing artificial intelligence
multimodal RAG document understanding
OCR error-aware retrieval
adaptive document classification

عدد الأوراق المطلوب
جمع 35 إلى 50 ورقة.
قراءة ملخصات جميعها.
قراءة 15 إلى 20 ورقة محورية بالكامل.
اعتماد 25 إلى 35 مرجعًا في الورقة النهائية.
توضيح هل المصدر ورقة محكمة أو Preprint.
6. جدول دراسة الأوراق

يُنشأ ملف Excel بالأعمدة التالية:

الحقل	المعلومات المطلوبةعنوان الورقة	الاسم الكامل
السنة	2022–2026
حالة الورقة	مجلة، مؤتمر، Preprint
لغة الوثائق	عربية، إنجليزية، متعددة
نوع الوثيقة	مطبوعة، مخطوطة، نماذج
المهمة	OCR، Layout، Classification، Retrieval
الخوارزمية	Tesseract، PaddleOCR، TrOCR، VLM
Dataset	عامة أو خاصة
عدد الصفحات	الحجم الفعلي
المعالجة	Deskew، Denoising، Binarization
مستوى التقسيم	صفحة أو وثيقة أو مجموعة
CER وWER	دقة OCR
mAP	تحليل التخطيط
Macro-F1	التصنيف
Recall@K وNDCG	البحث
زمن التنفيذ	لكل صفحة أو استعلام
الكود	متاح أو غير متاح
الرابط المجاني	PDF أو مستودع
القيود	أهم نقاط الضعف
الفجوة	إضافة المشروع
7. أحدث الخوارزميات المطلوب اختبارها
7.1 معالجة الصور
Orientation Detection.
Deskew.
Perspective Correction.
Adaptive Thresholding.
CLAHE.
Shadow Removal.
Denoising.
Border Removal.
Blank-page Detection.
Image Quality Assessment.

لكن لا تطبق Binarization على جميع الوثائق، لأنها قد تزيل الأختام الملونة والتوقيعات والكتابة الباهتة.

7.2 تحليل تخطيط الصفحة

يجب اكتشاف:

العناوين.
الفقرات.
الجداول.
الصور.
رأس الصفحة وتذييلها.
التوقيع.
الختم.
رقم الصفحة.
الأعمدة.
ترتيب القراءة.

الخوارزميات المقترحة:

YOLOv8 أو YOLO11.
Detectron2.
LayoutParser.
Docling.
LayoutLMv3.
PaddleOCR Layout Analysis.

تضم مجموعة DocLayNet عدد 80,863 صفحة مشروحة يدويًا، و11 فئة تخطيط، من مصادر تشمل الوثائق المالية والقانونية والبراءات والمناقصات والعلوم والكتيبات. كما توفر تقسيمات ثابتة للتدريب والتحقق والاختبار.

7.3 محركات OCR
خطوط المقارنة
Tesseract 5.
OCRmyPDF.
PaddleOCR.
EasyOCR.
TrOCR.
Docling.
نموذج Vision-Language محلي عند توفر GPU.

تُستخدم الأدوات التقليدية للصفحات النظيفة، بينما تُوجَّه الوثائق ذات التخطيط المعقد أو الجودة المنخفضة إلى محرك أقوى. الأدوات الحديثة لا تقتصر على قراءة الحروف، بل تعيد بناء الجداول وترتيب القراءة والبنية، وهو ما يهم مباشرة عند بناء فهرس صالح للبحث.

7.4 تصحيح OCR

يمكن استخدام نموذج لغوي لتصحيح أخطاء OCR، لكن مع قيود صارمة:

عدم استبدال النص الأصلي.
حفظ الفرق بين النصين.
منع تعديل الأرقام والتواريخ والأسماء تلقائيًا.
إحالة الحالات منخفضة الثقة إلى المراجع البشري.

قدمت مسابقة ICDAR 2026 HIPE-OCRepair إطارًا قابلًا لإعادة الإنتاج لتصحيح OCR التاريخي باستخدام النماذج اللغوية. وأظهرت أن النماذج الحديثة تحسن النص، لكن الإفراط في التصحيح للمدخلات الجيدة بقي مشكلة متكررة، ما يدعم الحاجة إلى بوابة ثقة قبل التصحيح.

7.5 تصنيف الوثائق

المقارنات المطلوبة:

TF-IDF + Linear SVM.
Logistic Regression.
XGBoost.
EfficientNet-B0 للصورة.
AraBERT أو نموذج عربي للنص.
LayoutLMv3 للنص والتخطيط.
نموذج متعدد الوسائط يجمع الصورة والنص والبيانات الوصفية.
7.6 البحث والفهرسة

يُقارن بين:

Exact keyword search.
BM25.
Dense Retrieval.
BM25 + Dense باستخدام Reciprocal Rank Fusion.
Cross-Encoder Reranking.
Visual Document Retrieval.
الفهرسة متعددة الوسائط.

أظهر MIDR: Enrichment-Augmented Indexing for Multimodal Document Retrieval، المقرر ظهوره في EMNLP 2026، أن نقل بعض الفهم متعدد الوسائط إلى وقت الفهرسة حقق متوسط nDCG مقداره 0.6219 على خمسة مجالات إنجليزية، بزيادة نسبية 23% على BM25، مع ذاكرة فهرس أصغر بنحو تسع مرات وزمن استعلام أقل بنحو الضعف من ColQwen2.5 ضمن تجارب الورقة.

كما اقترح Doc-REFRAG ضغط الرموز البصرية ثم توسيع المقاطع المرتبطة بالسؤال فقط، بهدف تقليل كلفة معالجة الصور غير المهمة في الوثائق الكبيرة. وقد قُبل العمل في EMNLP 2026.

8. مجموعات البيانات
8.1 DocLayNet

استخدامها:

تدريب أو Fine-tuning لتحليل التخطيط.
تقييم كشف النصوص والجداول والصور.
مقارنة YOLO وDetectron2.

تضم 69,375 صفحة تدريب، و6,489 للتحقق، و4,999 للاختبار ضمن التقسيم الرسمي.

8.2 Arabic Documents OCR Dataset

تضم 10 آلاف صورة عربية في 12 فئة، تشمل الكتابة اليدوية والفواتير والوثائق الرسمية والصحف والكتب والإيصالات والنماذج الإدارية والخرائط. تتضمن حدود الصفحة ومربعات النص والعناوين، ومتاحة تحت CC0 1.0.

8.3 SARD

تضم SARD عدد 843,622 صورة وثيقة عربية اصطناعية، ونحو 690 مليون كلمة، وعشرة خطوط عربية. وهي مفيدة للتدريب الأولي، لكنها نظيفة واصطناعية، ولذلك لا تكفي وحدها لاختبار أرشيف واقعي متدهور.

8.4 بيانات المؤسسة

هي الأهم للنشر الفعلي:

500 إلى 2,000 صفحة.
100 إلى 200 صفحة Ground Truth.
5 إلى 8 فئات.
50 إلى 100 استعلام بحث.
إزالة الأسماء والمعلومات الحساسة.
تقسيم البيانات حسب الوثيقة أو المجلد، لا حسب الصفحة عشوائيًا.
9. الخوارزمية الجديدة المقترحة
الاسم
SmartArchive-ARISE

Adaptive
 Routing,
 Indexing,
 Search and
 Evolving classification

تتكون من خمس وحدات:

Quality-Aware OCR Router.
Layout-Aware Text Reconstruction.
Reliability-Gated Multimodal Classification.
Confidence-Aware Hybrid Index.
Controlled Reclassification Engine.
10. Quality-Aware OCR Router

لكل صفحة pp، يحسب النظام:

Qp=w1Bp+w2Cp+w3Rp+w4Sp+w5LpQ_p = w_1B_p+ w_2C_p+ w_3R_p+ w_4S_p+ w_5L_p

حيث:

BpB_p: وضوح الصورة.
CpC_p: التباين.
RpR_p: دقة الصورة.
SpS_p: سلامة الميل والمنظور.
LpL_p: تعقيد التخطيط.

ثم يحدد المسار:

Route(p)={FastOCRQp≥0.80LayoutOCR0.55≤Qp<0.80AdvancedOCRQp<0.55HumanReviewCOCR<τRoute(p)= \begin{cases} FastOCR & Q_p \geq 0.80 \\ LayoutOCR & 0.55 \leq Q_p<0.80 \\ AdvancedOCR & Q_p<0.55 \\ HumanReview & C_{OCR}<\tau \end{cases}
المسارات
FastOCR

للوثائق النظيفة:

OCRmyPDF.
Tesseract.
PaddleOCR الخفيف.
LayoutOCR

للوثائق متعددة الأعمدة والجداول:

Docling.
PaddleOCR Layout.
Layout Detection + OCR per region.
AdvancedOCR

للصفحات الصعبة:

TrOCR.
VLM محلي.
Handwriting branch.

هذه العتبات قيم أولية تُضبط على مجموعة التحقق.

11. إعادة بناء النص من التخطيط

لكل عنصر مكتشف:

element_id
element_type
bounding_box
reading_order
language
raw_text
corrected_text
ocr_confidence
page_number


ثم يُعاد ترتيب النص:

من اليمين إلى اليسار للوثائق العربية.
من أعلى إلى أسفل.
مع فصل الأعمدة.
مع عدم دمج خلايا الجدول في فقرة واحدة.
مع ربط العنوان بالفقرات التابعة له.

تقييم OCR يجب ألا يقتصر على CER فقط؛ فمراجعة 2026 أوضحت أن المقاييس المعتادة قد لا تكشف انهيار الأعمدة أو أخطاء البنية أو النصوص المهلوسة في الوثائق التاريخية.

12. التصحيح المقيد بالثقة

يحفظ النظام:

ocr_raw_text
corrected_text
correction_diff
correction_confidence
review_status


تُحسب درجة التصحيح:

Ccorr=αPvisual+βPlanguage+γPdictionary+δPcontextC_{corr}= \alpha P_{visual} +\beta P_{language} +\gamma P_{dictionary} +\delta P_{context}

ولا يُقبل تلقائيًا إلا إذا:

Ccorr>τcC_{corr}>\tau_c
لا يُسمح بالتصحيح التلقائي لـ:
أرقام الكتب.
أرقام العقود.
المبالغ.
التواريخ.
الأسماء.
أرقام الهوية.
المواد القانونية.
التوقيعات.
13. التصنيف متعدد الوسائط
فرع الصورة
hv=fvision(page)h_v=f_{vision}(page)

استخدم:

EfficientNet-B0.
MobileViT.
ConvNeXt-Tiny.
فرع النص
ht=ftext(ocrText)h_t=f_{text}(ocrText)

باستخدام نموذج عربي أو متعدد اللغات.

فرع التخطيط
hl=flayout(elements,positions)h_l=f_{layout}(elements,positions)
فرع البيانات الوصفية
hm=fmetadata(date,sender,department,folder)h_m=f_{metadata}(date,sender,department,folder)
بوابة الدمج
g=Softmax(W[hv;ht;hl;hm])g= Softmax(W[h_v;h_t;h_l;h_m]) hf=g1hv+g2ht+g3hl+g4hmh_f= g_1h_v+g_2h_t+g_3h_l+g_4h_m

إذا كان OCR ضعيفًا، ينخفض وزن النص ويرتفع اعتماد النموذج على الصورة والتخطيط والمجلد.

14. التصنيف الهرمي

بدل فئة واحدة مسطحة:

Decision
Invoice
Contract
Letter
Report


يكون التصنيف:

Level 1:
Administrative / Financial / Legal / Technical

Level 2:
Decision / Contract / Invoice / Letter / Report

Level 3:
Department / Project / Confidentiality / Retention Category


ويحسب لكل مستوى احتمال مستقل.

إذا كان المستوى الأول واثقًا والثاني غير مؤكد:

Financial → Uncertain subtype → Human review

15. آلية إعادة التصنيف

هذه نقطة الجدة الأساسية في طلبك.

لا يُعاد تصنيف الوثيقة عند كل عملية بحث. بل يحدث ذلك عند ظهور دليل جديد:

استخراج Metadata جديدة.
تصحيح OCR.
إضافة علاقة بمشروع أو عقد.
اكتشاف نسخة أوضح.
إضافة فئة تنظيمية جديدة.
تغير نموذج التصنيف.
تعديل قاموس المؤسسة.
درجة التصنيف الجديد
Cnew=αPmodel+βMmetadata+γFfolder+δGrelations+ηHhistoryC_{new}= \alpha P_{model} +\beta M_{metadata} +\gamma F_{folder} +\delta G_{relations} +\eta H_{history}

ولا يُنفذ الانتقال إلا إذا:

Cnew−Cold>ΔC_{new}-C_{old}>\Delta

و:

Cnew>τreclassC_{new}>\tau_{reclass}
سياسة آمنة
High confidence:
    Suggest automatic reclassification

Medium confidence:
    Human approval required

Low confidence:
    Keep current class and log suggestion


يحفظ النظام:

old_class
new_class
reason
model_version
confidence
reviewer
timestamp

16. الفهرس الهجين الواعي بالثقة

لكل استعلام qq ومقطع dd:

Score(q,d)=αB(q,d)+βV(q,d)+γR(q,d)+δM(q,d)+ηF(q,d)+μO(d)+ρC(d)Score(q,d)= \alpha B(q,d) +\beta V(q,d) +\gamma R(q,d) +\delta M(q,d) +\eta F(q,d) +\mu O(d) +\rho C(d)

حيث:

BB: درجة BM25.
VV: التشابه الدلالي.
RR: Cross-Encoder Reranker.
MM: تطابق البيانات الوصفية.
FF: علاقة المجلد.
OO: جودة OCR.
CC: ثقة التصنيف.

قيم أولية:

BM25               = 0.20
Dense retrieval     = 0.20
Cross-encoder       = 0.25
Metadata            = 0.12
Folder relation     = 0.08
OCR confidence      = 0.10
Classification      = 0.05


تُضبط الأوزان باستخدام استعلامات التحقق.

17. لماذا نستخدم BM25 مع البحث الدلالي؟

BM25 أفضل غالبًا في:

رقم قرار.
رقم عقد.
اسم شخص أو شركة.
مادة قانونية.
رقم فاتورة.
عبارة حرفية.

أما Dense Retrieval فأفضل في:

البحث بالمعنى.
المرادفات.
الأسئلة الطبيعية.
النصوص التي لا تستخدم اللفظ نفسه.

ويعيد Cross-Encoder ترتيب أفضل النتائج بعد الاسترجاع الأولي.

18. دليل المجلد والرسم المعرفي

يمكن تحويل بنية الأرشيف إلى رسم معرفة:

العقد
Document.
Folder.
Organization.
Department.
Person.
Contract.
Project.
Decision.
Invoice.
Date.
العلاقات
DOCUMENT_IN_FOLDER
DOCUMENT_SENT_BY
DOCUMENT_SENT_TO
DOCUMENT_REFERENCES
INVOICE_RELATES_TO_CONTRACT
CONTRACT_BELONGS_TO_PROJECT
DECISION_SUPERSEDES_DECISION
DOCUMENT_HAS_VERSION


عند البحث عن عقد، يرفع النظام ترتيب:

الملاحق.
الفواتير.
المراسلات.
القرارات.
محاضر الاجتماعات المرتبطة به.
19. الإجابة الذكية

لا يجب أن يجيب النظام من ذاكرة نموذج لغوي عامة.

صيغة الإجابة
الإجابة:
تم تمديد مدة المشروع لمدة 90 يومًا.

المصدر:
القرار الإداري رقم 1542
الصفحة: 2
المقطع: الفقرة الثالثة

ثقة الاسترجاع: 0.92
ثقة OCR: 0.95
حالة الوثيقة: مراجعة بشريًا

[فتح الصفحة الأصلية]

بوابة الامتناع

يمتنع النظام إذا:

لم يجد مصدرًا واضحًا.
كانت ثقة OCR منخفضة.
تعارضت وثيقتان.
كان السؤال يتطلب استنتاجًا غير موجود.
لم يكن المستخدم مخولًا.
كانت الصفحة غير مراجعة والمعلومة حساسة.
اختلف الرقم بين النص الخام والمصحح.
20. تصميم المحاكاة والتجارب

المحاكاة تعني تشغيل النظام على وثائق حقيقية مع إنتاج نسخ مضبوطة الجودة، لا اختلاق النتائج.

مستويات الجودة
Clean
Mild degradation
Medium degradation
Severe degradation

التشويهات
دوران ±1، ±3، ±5 درجات.
Gaussian Blur.
Motion Blur.
JPEG Compression.
Shadow.
انخفاض التباين.
بقع واصفرار.
قص الحواف.
ضغط PDF.
دقة 150 و200 و300 و400 DPI.
ختم يغطي جزءًا من النص.
عمودان بدلاً من عمود واحد.

مع أن 300 DPI معيار عملي شائع للمسح القابل لـOCR، فإن المستندات الصغيرة أو القديمة قد تحتاج 400 أو 600 DPI، مع ارتفاع واضح في حجم الملفات ووقت المعالجة.

21. خطوط المقارنة
OCR
O1: Tesseract
O2: Tesseract + preprocessing
O3: PaddleOCR
O4: Layout-aware PaddleOCR
O5: TrOCR or VLM OCR
O6: SmartArchive adaptive routing

التصنيف
C1: TF-IDF + SVM
C2: XGBoost on text
C3: EfficientNet image-only
C4: Arabic text encoder
C5: Image + text
C6: Proposed gated multimodal classifier

البحث
R1: Exact keyword
R2: BM25
R3: Dense retrieval
R4: BM25 + Dense using RRF
R5: R4 + Cross-Encoder
R6: Proposed confidence-aware hybrid index

إعادة التصنيف
RC1: No reclassification
RC2: Model confidence only
RC3: Model + metadata
RC4: Model + metadata + folder evidence
RC5: Full controlled reclassification

22. دراسة الإزالة Ablation Study
A1: One OCR engine
A2: A1 + quality assessment
A3: A2 + layout analysis
A4: A3 + adaptive OCR routing
A5: A4 + constrained correction
A6: A5 + multimodal classification
A7: A6 + hybrid index
A8: Full SmartArchive-ARISE


وتزال العناصر منفردة:

Full system
- OCR confidence
- Layout representation
- Folder evidence
- Metadata matching
- Cross-encoder reranking
- Controlled reclassification

23. المقاييس العلمية
OCR
CER=S+D+INCER=\frac{S+D+I}{N} WER=Sw+Dw+IwNwWER=\frac{S_w+D_w+I_w}{N_w}

حيث:

SS: الاستبدال.
DD: الحذف.
II: الإضافة.
NN: عدد المحارف أو الكلمات المرجعية.
تحليل التخطيط
mAP@0.5.
Precision.
Recall.
F1.
Reading Order Accuracy.
Table Detection F1.
التصنيف
Macro-F1.
Weighted-F1.
Balanced Accuracy.
MCC.
Hierarchical F1.
Reclassification Precision.
Wrong-Move Rate.
البحث
Recall@5.
Recall@10.
Precision@5.
Mean Reciprocal Rank.
NDCG@10.
Correct Page Rate.
Query Latency.
الإجابة
Citation Correctness.
Faithfulness.
Answer Relevance.
Unsupported Claim Rate.
Abstention Accuracy.
الموارد
زمن OCR لكل صفحة.
صفحات في الدقيقة.
CPU وRAM وVRAM.
حجم الفهرس.
زمن الفهرسة.
P50 وP95 للاستعلام.
نسبة الصفحات المحولة للمراجعة البشرية.
24. أهداف النجاح

هذه أهداف هندسية وليست نتائج جاهزة:

CER أقل من 5% للوثائق المطبوعة النظيفة.
CER أقل من 15% للوثائق متوسطة التدهور.
Macro-F1 أعلى من 0.85 للتصنيف.
Wrong Reclassification Rate أقل من 3%.
Recall@10 أعلى من 0.90.
تحسن NDCG@10 بنسبة 5% على الأقل على BM25.
Correct Page Rate أعلى من 90%.
Unsupported Claim Rate أقل من 3%.
P95 Search Latency أقل من ثانيتين.
تحويل أقل من 25% من الصفحات للمراجعة.
عدم فقد أي ملف أصلي أو سجل تعديل.
25. الاختبارات الإحصائية
خمس بذور عشوائية للتصنيف.
Bootstrap من 1,000 إلى 2,000 عينة.
Wilcoxon Signed-Rank لمقارنة CER وWER.
McNemar لمقارنة التصنيف وإعادة التصنيف.
Friedman Test لمقارنة عدة نماذج.
Holm-Bonferroni للمقارنات المتعددة.
Paired Bootstrap لمقارنة NDCG وRecall.
Cliff’s Delta لحجم الأثر.

يجب تنفيذ Bootstrap على مستوى الوثيقة، لا الصفحة فقط، لأن صفحات الوثيقة الواحدة مترابطة.

26. البنية البرمجية
Upload / Scanner
        ↓
Original File Preservation + SHA-256
        ↓
Page Rendering
        ↓
Quality Assessment
        ↓
Layout Detection
        ↓
Adaptive OCR Router
        ↓
Raw Text + Bounding Boxes
        ↓
Constrained Correction
        ↓
Metadata and Entity Extraction
        ↓
Multimodal Classification
        ↓
Duplicate and Version Detection
        ↓
BM25 + Dense + Metadata + Folder Index
        ↓
Cross-Encoder Reranking
        ↓
Grounded Answer + Page Citation
        ↓
Controlled Reclassification

Backend
Python 3.11.
FastAPI.
PostgreSQL.
Redis.
Celery.
MinIO.
OpenSearch أو Elasticsearch.
Qdrant أو PostgreSQL + pgvector.
Neo4j اختياري.
معالجة الوثائق
OpenCV.
OCRmyPDF.
Tesseract.
PaddleOCR.
Docling.
PyMuPDF.
pdfplumber.
LayoutParser.
Detectron2 أو YOLO.
الذكاء الاصطناعي
PyTorch.
Transformers.
sentence-transformers.
AraBERT.
XGBoost.
SHAP.
Cross-Encoder.
MLflow.
Optuna.
الواجهة
React أو Next.js.
أو Streamlit للنسخة المختصرة.
عارض PDF.
دعم RTL.
تمييز Bounding Box للمقتطف المسترجع.
شاشة مراجعة للتصنيف والتصحيح.
سجل تاريخ الوثيقة.
27. قاعدة البيانات الأساسية
users
roles
documents
document_versions
pages
layout_elements
ocr_runs
ocr_text_blocks
ocr_corrections
document_classes
classification_history
metadata_fields
entities
folders
folder_relations
document_relations
search_chunks
embeddings
search_queries
retrieval_results
human_reviews
audit_logs
retention_rules

سجل إعادة التصنيف
document_id
old_class
proposed_class
model_version
confidence
supporting_evidence
review_status
reviewer_id
timestamp

28. حفظ الملف بصورة صحيحة

يُحفظ لكل وثيقة:

Preservation Master
الأصل دون تعديل.
SHA-256.
صلاحيات مقيدة.
لا يستخدم للتصفح اليومي.
Access Copy
PDF قابل للبحث.
حجم مناسب للاستخدام.
Watermark عند الحاجة.
Structured Copy
JSON
Plain text
PAGE-XML or ALTO-XML
Bounding boxes
Metadata
Embeddings
Classification history


ولا يُحذف المستند الورقي أو الأصل الرقمي بناءً على النموذج الأولي وحده.

29. البرنامج الزمني لشهر ونصف
الأسبوع الأول: الأدبيات والبيانات
اليوم 1
تثبيت أنواع الوثائق.
إنشاء Git Repository.
وضع سياسة الخصوصية.
تحديد المقاييس.
اليومان 2–3
جمع 35–50 ورقة.
ملء جدول الدراسات.
تنزيل الأوراق المجانية.
اليومان 4–5
قراءة 15–20 ورقة محورية.
تثبيت SmartArchive-ARISE.
كتابة Related Work الأولي.
اليومان 6–7
جمع 500–2,000 صفحة.
اختيار 100–200 صفحة Ground Truth.
تعريف فئات التصنيف.
وضع تقسيم Train/Validation/Test.

المخرج: مراجعة أولية وبيانات منظمة.

الأسبوع الثاني: OCR والتخطيط
حفظ الأصل وSHA-256.
معالجة الصور.
تشغيل Tesseract وPaddleOCR.
بناء Quality Assessment.
تدريب أو تكييف Layout Detector.
حفظ النصوص والإحداثيات.
حساب CER وWER.

المخرج: خط رقمنة كامل.

الأسبوع الثالث: التصنيف وMetadata
TF-IDF + SVM.
EfficientNet.
Arabic Text Encoder.
بناء Multimodal Gating.
استخراج التواريخ والأرقام والجهات.
كشف التكرار.
إنشاء واجهة المراجعة.

المخرج: تصنيف واستخراج Metadata.

الأسبوع الرابع: البحث وإعادة التصنيف
إنشاء BM25.
إنشاء Dense Index.
تنفيذ RRF.
إضافة Cross-Encoder.
إضافة Folder Evidence.
بناء Reclassification Engine.
إضافة Answer Abstention.
عرض الصفحة الأصلية والمقطع.

المخرج: بحث هجين وإعادة تصنيف مضبوطة.

الأسبوع الخامس: المحاكاة والتقييم
توليد نسخ مشوهة.
مقارنة مسارات OCR.
تقييم التصنيف.
تقييم إعادة التصنيف.
تشغيل 50–100 استعلام.
Ablation Study.
قياس الأداء والذاكرة.
Bootstrap والاختبارات الإحصائية.
تحليل حالات الفشل.

المخرج: نتائج نهائية وجداول ورسوم.

نصف الأسبوع السادس: الورقة
اليومان 36–37
Methodology.
Architecture.
Proposed Algorithm.
Dataset.
اليومان 38–39
OCR Results.
Classification Results.
Retrieval Results.
Reclassification Results.
اليومان 40–41
Ablation.
Performance.
Security.
Limitations.
اليومان 42–43
Abstract.
Conclusion.
تنسيق المراجع.
تدقيق الأرقام.
تجهيز الكود والملحق.
اختيار المجلة.
إعداد Cover Letter.
30. بنية الورقة العلمية
العنوان

SmartArchive-ARISE: Adaptive OCR Routing, Multimodal Classification, and Confidence-Aware Hybrid Indexing for Arabic Archives

الأقسام
Abstract
Introduction
Related Work
Research Questions
Dataset and Digitization Protocol
System Architecture
Adaptive OCR Routing
Layout-Aware Text Reconstruction
Multimodal Hierarchical Classification
Confidence-Aware Hybrid Indexing
Controlled Reclassification
Experimental Setup
OCR Results
Classification Results
Retrieval Results
Ablation and Resource Analysis
Security, Privacy, and Preservation
Limitations
Conclusion
المساهمات بصياغة جاهزة

We design and implement an end-to-end Arabic document-archiving platform that preserves original files while producing searchable PDFs, structured text, metadata, layout annotations, and version histories.

We propose a quality-aware OCR routing mechanism that adaptively selects lightweight, layout-aware, or advanced recognition paths according to page quality and structural complexity.

We introduce a reliability-gated multimodal classifier that combines page appearance, OCR text, layout, metadata, and archival-folder evidence.

We develop a confidence-aware hybrid index combining BM25, dense retrieval, cross-encoder reranking, OCR confidence, metadata, and folder relationships.

We propose a controlled reclassification mechanism that updates archival categories only when the confidence gain and supporting evidence exceed predefined thresholds.

We evaluate the framework using controlled document degradation, OCR benchmarks, hierarchical classification, retrieval tests, reclassification analysis, and resource measurements.

31. الأوراق المجانية الأساسية
Scaling Beyond Context: A Survey of Multimodal Retrieval-Augmented Generation for Document Understanding، منشورة ضمن ACL 2026، ومناسبة لبناء خريطة خوارزميات Multimodal RAG والبيانات والمقاييس.
MIDR: Enrichment-Augmented Indexing for Multimodal Document Retrieval، ستظهر في EMNLP 2026، ومهمة لفكرة إثراء الوثيقة وقت الفهرسة مع تقليل كلفة الاستعلام.
Doc-REFRAG: Rethinking Multimodal Document Retrieval-Augmented Generation، مقبولة في EMNLP 2026، ومناسبة لفكرة انتقاء المقاطع البصرية المرتبطة بالسؤال.
ICDAR 2026 HIPE-OCRepair Competition on LLM-Assisted OCR Post-Correction for Historical Documents، لتصميم التصحيح المقيد وتقييم الإفراط في التصحيح.
A Survey of OCR Evaluation Methods and Metrics and the Invisibility of Historical Documents، لتصميم تقييم يتجاوز CER ويشمل التخطيط والبنية.
DocLayNet: A Large Human-Annotated Dataset for Document-Layout Analysis، لتحليل التخطيط والتجارب المرجعية.
SARD: A Large-Scale Synthetic Arabic OCR Dataset for Book-Style Text Recognition، لتدريب واختبار OCR العربي.
Arabic Documents OCR Dataset، وهي مجموعة عربية مفتوحة بـ10 آلاف صورة و12 فئة وثائقية.
32. المجلات المحتملة
International Journal on Document Analysis and Recognition

هذا الخيار الأكثر تخصصًا في OCR وتحليل الوثائق؛ نطاقها يشمل التعرف على النصوص والرموز والكتابة اليدوية والتوقيعات وتحليل البنية الفيزيائية والمنطقية للوثيقة. كما يذكر موقع الناشر أنها مفهرسة في Scopus.

وهي الأنسب إذا ركزت الورقة على:

OCR Routing.
Layout Analysis.
Arabic Document Recognition.
Multimodal Classification.
Dataset أو Benchmark جديد.
International Journal on Digital Libraries

نطاقها يشمل إدارة المعلومات الرقمية وحفظها واكتشافها، البيانات الوصفية، الأرشفة، البحث الذكي، الذكاء الاصطناعي في المكتبات الرقمية، والخصوصية.

وهي الأنسب إذا ركزت الورقة على:

بنية منصة الأرشيف.
الفهرسة.
إعادة التصنيف.
الرسم المعرفي.
الحفظ والـProvenance.
تجربة المستخدم والوصول.
Information Processing & Management

خيار طموح إذا كانت المساهمة الأساسية خوارزمية بحث واسترجاع قوية مع تقييم واسع. تظهر المصادر المتاحة تصنيفها ضمن Q1 وتغطيتها النشطة في Scopus، لكن المنافسة فيها مرتفعة وتحتاج إلى أكثر من نموذج موقع تجريبي صغير.

خيارات إضافية
Journal of Documentation.
Multimedia Tools and Applications.
Applied Intelligence.
Expert Systems with Applications.
Journal of Imaging.
Digital Scholarship in the Humanities.

يجب التحقق من اسم المجلة وISSN واستمرار الفهرسة والربع داخل Scopus Sources في يوم التقديم، لأن التصنيفات والرسوم قد تتغير.

33. الحد الأدنى القابل للتسليم

بنهاية الشهر والنصف يجب أن يتوفر:

مراجعة 35–50 ورقة.
جدول مقارنة خوارزميات.
500 صفحة على الأقل.
100 صفحة Ground Truth.
حفظ أصل وبصمة SHA-256.
3 مسارات OCR.
تحليل تخطيط.
نص خام ومصحح.
5 أنواع وثائق.
3 Baselines للتصنيف.
نموذج تصنيف متعدد الوسائط.
BM25.
Dense Retrieval.
Cross-Encoder.
Folder Knowledge Graph مبسط.
Confidence-Aware Index.
Reclassification Engine.
50 استعلامًا مقيمًا يدويًا.
Ablation Study.
نتائج CER وWER وMacro-F1 وNDCG.
واجهة عربية RTL.
عرض الصفحة والدليل.
صلاحيات وتدقيق.
مستودع كود منظم.
مسودة ورقة باللغة الإنجليزية.
القرار التنفيذي النهائي

أفضل صيغة للمشروع هي:

منصة SmartArchive-X لحفظ الوثائق الأصلية، تحليل جودة الصفحات وتوجيهها إلى محرك OCR مناسب، إعادة بناء النص حسب التخطيط، تصنيف الوثائق بالاعتماد على الصورة والنص والبيانات الوصفية، ثم إنشاء فهرس هجين يجمع BM25 والبحث الدلالي وإعادة الترتيب وثقة OCR وعلاقة المجلد، مع إعادة تصنيف مضبوطة عند ظهور دليل جديد.

القيمة العلمية الحقيقية ستكون إثبات أن:

التوجيه التكيفي يقلل CER ووقت المعالجة.
دمج الصورة والنص والتخطيط يحسن التصنيف.
ثقة OCR والـMetadata تحسنان ترتيب البحث.
إعادة التصنيف المضبوطة تقلل النقل الخاطئ للوثائق.
بوابة الامتناع تقلل الإجابات غير المسندة.
النظام يحافظ على الأصل وسجل التعديلات ولا يعتبر النص المصحح وثيقة رسمية دون مراجعة.