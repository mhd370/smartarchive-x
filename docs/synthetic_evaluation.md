# Synthetic evaluation results (Sprints 6–8)

All numbers are on **synthetic** documents (ADR 0008) and must be reported as such. Tesseract 5.5.3. Metric
policy `normalized-v1`: diacritics and tatweel ignored on both sides. Reproduce with the commands in the README.

## Development set `corpus_v1` (seed 2026): 490 files, 499 pages, 8 types

### OCR ablation (CER, micro-averaged over pages)

| Configuration | All | Born-digital | Clean | Mild | Medium | Severe | Tables | Two columns |
|---|---|---|---|---|---|---|---|---|
| `ara+eng`, PDF 300 dpi, illumination fix | 30.3% | 18.6% | 13.9% | 12.4% | 37.9% | 92.4% | 46.8% | 34.3% |
| `script/Arabic+ara`, PDF 300 dpi | 28.5% | 17.1% | 12.3% | 11.1% | 32.4% | 92.2% | 45.7% | 32.9% |
| **`script/Arabic+ara`, PDF 200 dpi** (chosen) | **26.1%** | **12.9%** | **9.9%** | **10.5%** | **30.6%** | 92.3% | **40.8%** | **31.0%** |

Illumination fix, paired on the same 30 documents with `ara+eng` (mean document CER, before → after):
- all: 49.0% → 34.7%
- medium: 99.4% → 40.0%
- severe: 100% → 88.0%
- clean, mild and born-digital: unchanged

Before the fix, a shaded page was mostly counted as ink, so a 3° tilt was measured as 10.5°. The wrong
deskew made the page unreadable.

Findings that set the next work:
- **Arabic-Indic digits.** `ara` knows only ٠ and ١, and `script/Arabic` reads digits but often in the wrong
  order around slashes. Exact reference numbers stay below 10% with every model, so a second engine is
  needed.
- **Severe scans** (150 dpi, strong blur) are not readable by Tesseract with any preprocessing tried. They are
  the target of the advanced OCR route.
- **Tables and two-column pages** are 10–20 points worse than simple pages. Reading order needs layout
  analysis.
- **Render resolution.** Tesseract's Arabic models read PDF pages rendered at 200 dpi better than at 300 dpi
  (born-digital 17.1% → 12.9%). The default is now 200.

### Metadata, relations and search (same OCR text, rules before → after)

| Measure (`ara+eng` OCR) | rules-v1 / fingerprint-v1 | rules-v2 / fingerprint-v2 |
|---|---|---|
| Metadata exact match, all fields written in the document | 21.3% | 27.2% |
| Subject exact match | 16.9% | 48.7% |
| Relation suggestions: precision (any relation) | 56.5% | 100% |
| Version suggestions linking unrelated documents | 25 | 0 (5 remain; all are true near-duplicates) |

The chosen OCR configuration with v2 rules gives:
- Metadata exact match 28.6%, with subject 55.0%, recipient 42.5% and date 39.6%.
- Reference numbers 1.4% and amounts 9.8% (limited by digit OCR).
- Search over 321 queries: Recall@10 51.2%, MRR@10 31.0%, nDCG@10 34.7%.
- Classification (`keywords-v1`): accuracy 71.4% and coverage 79.0%; precision on answered documents 90.4%;
  first level (group) 80.8%.
- Relations: 26 suggestions, 92.3% correct. All 20 exact duplicates are found, but only 1 of 27 near-duplicates
  and none of the 23 versions: the text differs too much after OCR, and the reference numbers that would
  link versions are misread.

## Test set `corpus_v2` (seed 7351): 606 files, 624 pages

Run once with the configuration chosen on the development set (`script/Arabic+ara`, PDF 200 dpi, rules-v2,
fingerprint-v2). Nothing was tuned on it.

| OCR (CER / WER) | Pages | CER | WER |
|---|---|---|---|
| All | 624 | 27.5% | 36.7% |
| Born-digital | 248 | 11.4% | 16.6% |
| Clean scans | 92 | 14.4% | 20.0% |
| Mild | 92 | 14.0% | 18.6% |
| Medium | 98 | 29.8% | 57.8% |
| Severe | 94 | 93.0% | 99.9% |
| Simple layout / two columns / tables | 389 / 81 / 154 | 22.9% / 32.6% / 40.7% | 32.8% / 41.6% / 47.3% |

| Task | Result |
|---|---|
| Metadata exact match (2,874 fields written in the documents) | 26.7%: subject 51.2%, recipient 39.8%, date 36.8%, sender 16.2%, amount 8.8%, reference number 1.7% |
| Classification (`keywords-v1`) | accuracy 71.6%, coverage 76.4%, precision when answered 93.7%, group 80.4% |
| Relations (86 true) | 30 suggested, all correct; exact duplicates 28/28; near-duplicates 0/25; versions 0/33 |
| Search (430 queries) | Recall@10 46.2%, MRR@10 26.2%, nDCG@10 30.4% (subjects: Recall@10 60.5%; reference numbers: 8.8%) |

The test numbers are within about 1.5 points of the development set (CER 27.5% vs 26.1%, metadata 26.7% vs
28.6%), so the rule changes did not overfit corpus_v1. The ranking of weaknesses is the same: Arabic-Indic
digits, severe scans and table reading order.

## Sprint 7: ranked search (development set, same OCR text, `ara+eng`)

| Search mode | Recall@10 | MRR@10 | nDCG@10 | Subjects R@10 | Reference numbers R@10 |
|---|---|---|---|---|---|
| exact (substring-v1, every word) | 44.2% | 30.9% | 33.3% | 55.2% | 12.2% |
| BM25 stems + trigrams (no exact ranking) | 51.6% | 28.5% | 33.2% | 58.4% | 31.7% |
| **hybrid-rrf-v1** (exact + BM25 stems + trigrams) | **54.2%** | **33.4%** | **37.7%** | **62.3%** | **30.5%** |

BM25 alone raised recall but lowered MRR: many documents share most subject words, and only the whole-phrase
signal separates them. Adding the exact ranking to the fusion recovered and exceeded the old MRR. The exact
mode stays available.

Same comparison on `script/Arabic+ara` OCR text, the configuration chosen for OCR (Sprint 8):

| Set | exact R@10 / MRR / nDCG | hybrid-rrf-v1 R@10 / MRR / nDCG | Reference numbers R@10 (both) |
|---|---|---|---|
| Development corpus_v1 (321 queries) | 51.2% / 31.0% / 34.7% | 51.4% / 33.6% / 36.9% | 6.7% |
| Test corpus_v2 (430 queries) | 46.2% / 26.2% / 30.4% | 46.3% / 27.3% / 31.5% | 8.8% |

The ranked search behaves the same on both sets, so it was not fitted to corpus_v1. The large gain above came
from the `ara+eng` text: that model misreads more words, and the trigram ranking recovered them. The
`script/Arabic` model reads words better, so exact matching already finds more (51% against 44%) and fusion adds
little recall; it still ranks the right document higher (MRR +1 to +2.6 points). Reference numbers are the open
problem: the OCR digit error is about 50%, and no ranking recovers a number that was read wrongly.

## Sprint 8: learned classifier (`tfidf-svm-v1`, ADR 0010)

Trained once on all of corpus_v1's OCR text (440 documents, 49–58 per type), then applied to corpus_v2 with
the same stored OCR text as the keyword run (`--classifier-model`, `--re-enrich`).

| Test set corpus_v2 (606 documents) | keywords-v1 | tfidf-svm-v1 |
|---|---|---|
| Accuracy (abstentions count as wrong) | 71.6% | **81.0%** |
| Coverage (documents answered) | 76.4% | **82.7%** |
| Precision when answered | 93.7% | **98.0%** |
| First level (group) | 80.4% | **86.8%** |
| Born-digital / clean / mild | 85.1% / 87.8% / 91.1% | 99.2% / 97.8% / 100% |
| Medium scans | 60.6% | 76.6% |
| Severe scans | 12.1% | 2.2% |

Development set, 5-fold grouped cross-validation: accuracy 82.9%, coverage 82.9%, precision 96.8%. The test
result is within 2 points, so the model generalizes across corpora generated with different seeds. On severe
scans the OCR text is almost empty, and the model abstains more often than the keywords did. It answers too
few of them to be useful either way: these pages need better OCR or image features, not a better text model.

