# Synthetic evaluation results (Sprints 6–10)

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

Same comparison on `script/Arabic+ara` OCR text, the configuration chosen for OCR. **Correction (Sprint 10):**
the Sprint 8 version of this table reported ranked ≈ exact on both sets. That was a measurement error, not a
property of the search. `tools/evaluate_synthetic.py` scored archives that had been OCR'd before ranked search
existed without back-filling their ranked indexes, which the API does at start-up. Ranked search then ran on
the exact signal alone. The evaluator now back-fills before scoring. The corrected runs, without layout analysis:

| Set | exact R@10 / MRR / nDCG | hybrid-rrf-v1 R@10 / MRR / nDCG | Reference numbers R@10 exact → ranked |
|---|---|---|---|
| Development corpus_v1 (321 queries) | 51.2% / 31.0% / 34.7% | **60.1% / 37.1% / 41.9%** | 6.7% → **35.4%** |
| Test corpus_v2 (430 queries) | 46.2% / 26.2% / 30.4% | **54.2% / 31.4% / 36.1%** | 8.8% → **29.8%** |

Ranked search adds 8–9 points of Recall@10 on both sets. Most of the gain is on reference numbers. The Sprint 8
conclusion that the gain came only from the noisier `ara+eng` text is withdrawn. **Correction (Sprint 12):** this
paragraph first credited the trigram ranking for the reference-number gain. The component ablation of Sprint 12
shows that the gain comes from BM25 over the word index, which lets any part of the number match; adding the
trigram ranking lowers reference-number recall.

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

## Sprint 10: layout analysis (`layout-v1`, ADR 0012)

Full OCR runs again with layout analysis (`--work corpus_v1_layout`, `corpus_v2_layout`), compared with the
earlier runs without it. Same Tesseract 5.5.3, `script/Arabic+ara`, 200 dpi.

| CER | Dev without | Dev with | Test without | Test with |
|---|---|---|---|---|
| All pages | 26.1% | **24.6%** | 27.5% | **25.8%** |
| Tables | 40.8% | **33.6%** | 40.7% | **33.3%** |
| Two columns | 31.0% | **29.1%** | 32.6% | **30.4%** |
| Simple | 21.3% | 21.3% | 22.9% | 22.7% |
| Born-digital | 12.9% | **10.9%** | 11.4% | **10.5%** |
| Severe scans | 92.3% | 92.3% | 93.0% | 93.0% |

On the test set, layout analysis also changes these:
- classification (`tfidf-svm-v1`) 81.0% → 81.5%, still 98.0% precise when answered;
- ranked search Recall@10 54.2% → 54.9%, reference numbers unchanged at 29.8%.

The gain is smaller than on the 29-page development sample used to build it, where tables went from 22% to 12%.
On medium and severe scans the ruling lines are often too broken to be found, and those pages keep psm 3. Simple
pages are unchanged in both sets, so the detector does not misfire on them.

### Second OCR engines (development sample, 40 pages)

| Engine | CER | Digit CER | s/page | Born-digital | Clean | Mild | Medium | Severe |
|---|---|---|---|---|---|---|---|---|
| Tesseract 5.5.3 `script/Arabic+ara` | **30.8%** | **52.6%** | **3.2** | 10.3% | **6.1%** | 14.5% | **30.5%** | **85.8%** |
| PaddleOCR 3.7 (PP-OCRv5 mobile, Arabic) | 40.9% | 72.9% | 22.5 | 8.6% | 24.5% | 9.5% | 54.4% | 98.7% |
| EasyOCR 1.7.2 | 43.2% | 53.8% | ≈ 120* | **7.6%** | 21.7% | **6.3%** | 74.7% | 100% |

\* EasyOCR was measured at about 2 minutes per page on this CPU. The logged figure is inflated by the laptop
sleeping during the run.

Tesseract stays the engine. The other two read born-digital and mildly degraded pages slightly better. With 8
pages per quality level that is not conclusive, and they are 7–40× slower and much worse on scans.

## Sprint 11: dense retrieval, paraphrased queries, third classification baseline

### Search with paraphrased queries (ADR 0013)
`tools/paraphrase_queries.py` rewrites every subject query with fixed synonym rules, keeping names: 239
development queries and 311 test queries. Results are Recall@10 / MRR@10 on layout-analysis OCR text.

| Queries | Dev lexical | Dev + dense | Test lexical | Test + dense |
|---|---|---|---|---|
| Original | 60.9% / 37.6% | 61.8% / 37.8% | 54.9% / 32.5% | 54.5% / 30.1% |
| Paraphrased | 34.1% / 14.5% | 40.8% / 19.0% | 33.4% / 14.9% | 33.9% / 14.7% |
| Paraphrased, exact mode | 2.1% | — | 3.4% | — |

The development gain from dense retrieval (+6.7) does not carry over to the test set (+0.5). Dense retrieval is
therefore off by default.

### Three classification baselines (test set corpus_v2, 606 documents)
The learned models were trained on corpus_v1's layout-analysis OCR text.

| Baseline | Accuracy | Coverage | Precision when answered | Group |
|---|---|---|---|---|
| `keywords-v1` | 71.6% | 76.4% | 93.7% | 80.4% |
| `tfidf-svm-v1` (default) | **81.2%** | 82.8% | **98.0%** | 87.1% |
| `tfidf-char-lr-v1` | 79.7% | **83.2%** | 95.8% | **87.3%** |

The character model answers slightly more documents but is wrong more often, and on an archive a wrong
category costs more than an abstention. Development-set cross-validation (OCR text, 5 folds grouped by
relation cluster) agrees:
- word SVM: 87.3% accuracy without abstention, 97.6% precision at the 0.4 threshold;
- character model: 86.3% and 96.2%.

Neither text model helps severe scans, which reach 31–37% in cross-validation because their OCR text is almost
empty.

### Reclassification gates on held-out data (ADR 0011)
With `tfidf-svm-v1` on the test set:
- 78.5% of wrong confirmations caught;
- 0.3% false alarms on correct confirmations;
- 0.3% proposals to another wrong type.

These match the development figures used to choose the gates (76.7% / 0.2% / 0.17%).


## Sprint 12: macro-F1, multimodal classification, folder suggestion, search ablation and re-ranking

### Classification with macro-F1 and the page image (ADR 0015)
`tools/classification_experiments.py`, test set corpus_v2 (606 documents). Every model was trained on corpus_v1
layout-analysis OCR text and its page images. The fusion weight β was chosen by 5-fold cross-validation on
corpus_v1.

| Model | Accuracy | Coverage | Precision when answered | Macro-F1 | Medium scans | Severe scans |
|---|---|---|---|---|---|---|
| `keywords-v1` | 71.8% | 76.6% | 93.8% | 79.6% | 60.6% | 12.1% |
| `tfidf-svm-v1` | 81.2% | 82.8% | **98.0%** | 88.8% | 77.7% | 1.1% |
| `tfidf-char-lr-v1` | 79.7% | 83.2% | 95.8% | 87.1% | 77.7% | 2.2% |
| `visual-layout-v1`, image only | 73.4% | 87.5% | 84.0% | 77.2% | 51.1% | 44.0% |
| **SVM + image, late fusion (β = 1)** | **89.6%** | 94.1% | 95.3% | **92.3%** | 85.1% | 46.2% |
| SVM, image only where the SVM abstains (gated, β = 2) | **90.4%** | **98.4%** | 92.0% | 91.2% | **89.4%** | **50.5%** |

Born-digital, clean and mild pages stay at 99–100% with both fusions.

Development cross-validation chose β:

| β | 0 | 0.25 | 0.5 | 1 | 2 |
|---|---|---|---|---|---|
| Late fusion | 81.8% | 83.3% | 84.7% | **86.7%** | 86.3% |
| Gated | 81.8% | 83.1% | 84.5% | 87.1% | **88.4%** |

Findings:
- **The page image recovers what OCR loses.** On severe scans, where the text models are right on 1–2% of
  documents, layout alone is right on 44%. Fused with the SVM it reaches 46–50%.
- **Precision is the cost.** Fusion answers 94–98% of documents instead of 83%, but precision when answered falls
  from 98.0% to 92–95%: the image answers documents the text model left to a reviewer, and some of those
  answers are wrong.
- **Choosing a fusion.** Late fusion has the best macro-F1 (92.3%) and keeps precision above 95%, so it is the
  recommended setting. The gated variant answers more documents, at lower precision.

### Folder suggestion (test set, leave-one-out over 606 documents, 6 department folders)

| Method | Correct department |
|---|---|
| Always the most common folder | 22.3% |
| The folder most used for the document's predicted type | 43.7% |
| **`folder-knn-v1`: the 5 most similar documents vote (TF-IDF cosine)** | **58.6%** |
| The same, correct folder among the 3 shown | **81.5%** |

Department folders overlap in the types they hold, so the type alone cannot place a document. The documents'
own words do better. The UI shows three suggestions and leaves the move to a person.

### Search ablation and confidence-aware fusion (ADR 0014)
`tools/search_experiments.py` on the stored layout-analysis OCR text, the same document-level ranked search as
the API. Recall@10 / MRR@10.

| Rankings fused | Dev: all | Dev: reference numbers | Test: all | Test: subjects | Test: reference numbers | Test: paraphrased |
|---|---|---|---|---|---|---|
| exact only | 51.4% / 33.7% | 6.7% / 6.7% | 46.2% / 27.1% | 60.8% / 34.8% | 8.0% / 7.0% | 3.7% / 1.7% |
| BM25 stems only | 63.9% / 37.1% | 54.3% / 32.3% | 55.1% / 32.0% | 60.9% / 33.7% | 39.9% / 27.7% | 31.0% / 13.5% |
| trigrams only | 53.4% / 30.8% | 24.4% / 22.9% | 47.8% / 27.1% | 58.0% / 30.8% | 21.0% / 17.3% | 30.1% / 13.0% |
| **exact + stems (new default, `hybrid-rrf-v3`)** | **65.3% / 39.9%** | 53.0% / 31.2% | **58.1% / 33.0%** | 64.8% / 35.4% | **40.8% / 26.7%** | 33.4% / 15.1% |
| exact + trigrams | 59.7% / 38.1% | 25.6% / 23.7% | 53.1% / 30.9% | 64.8% / 36.0% | 22.7% / 17.5% | 32.8% / 14.5% |
| stems + trigrams | 56.9% / 32.8% | 36.0% / 26.0% | 50.6% / 28.9% | 59.5% / 31.6% | 27.3% / 22.0% | 31.0% / 13.6% |
| exact + stems + trigrams (`hybrid-rrf-v1`, Sprints 7–11) | 60.9% / 37.6% | 37.2% / 26.8% | 54.9% / 32.5% | 64.5% / 36.2% | 29.8% / 22.7% | 33.4% / 14.9% |
| the same + confidence-aware fusion, α = 0.25 | 60.6% / 37.1% | 36.0% / 25.2% | 54.6% / 32.0% | 64.5% / 36.2% | 29.0% / 20.9% | 32.8% / 15.4% |

nDCG@10 over the original queries: exact + stems 45.1% (dev) and 38.4% (test), against 42.5% and 37.0% for the
three-way fusion.

Findings:
- **The trigram ranking hurts.** Every fusion that includes it is below the same fusion without it, on both
  sets and for reference numbers most of all (test 40.8% → 29.8%). A likely reason is that trigrams of digits
  and of common words are shared by many documents and push the right one out of the top 10. The word index
  already tolerates OCR errors in its own way, because any query word may match.
- **The reference-number gain comes from BM25 over the word index:** exact search finds 8.0%, stems alone
  39.9%.
- **New default.** On the development set exact + stems was best by nDCG@10. The test set confirmed it (+3.2
  points Recall@10, +0.5 MRR over the old default), so it became the default. Trigrams stay available
  (`SMARTARCHIVE_SEARCH_COMPONENTS`).
- **Confidence-aware fusion does not help.** The best weight on the development set, α = 0.25, was below the
  plain fusion there and on the test set. It stays off (`SMARTARCHIVE_CONFIDENCE_ALPHA=0`), a measured negative
  result. A likely reason is that page-level confidence is too coarse: a page with a low mean confidence can
  still hold the query's words intact.

### Cross-encoder re-ranking (ADR 0014)
`ce-mminilm-v1` re-orders the top 20 documents of the three-way fusion (`exact + stems + trigrams`), fused with
the hybrid rank by RRF. Recall@10 / MRR@10.

| | Original queries | Reference numbers | Paraphrased | s/query |
|---|---|---|---|---|
| Dev: three-way fusion | 60.9% / 37.6% | 37.2% / 26.8% | 34.1% / 14.5% | 0.03 |
| Dev: + cross-encoder | **64.2% / 38.8%** | — | **48.3%** / — | 2.5 |
| Test: three-way fusion | 54.9% / 32.5% | 29.8% / 22.7% | 33.4% / 14.9% | 0.08 |
| Test: + cross-encoder | 55.4% / **34.0%** | 32.4% / 26.3% | **43.4% / 20.9%** | 3.1 |
| Test: exact + stems (default, no re-ranking) | **58.1%** / 33.0% | **40.8%** / 26.7% | 33.4% / 15.1% | 0.08 |

The development log printed only the summary line for the re-ranked run, so its per-kind cells are left
empty. The `replace` mode was not measured: the laptop went to sleep during that run, and the test set was run
in `fuse` mode only.

Findings:
- **The re-ranker generalizes.** Unlike dense retrieval, it keeps most of its development gain on paraphrased
  queries: +10.0 points of Recall@10 and +6.0 of MRR on the test set, against +14.2 on the development set. It
  also raises MRR on the original queries (32.5% → 34.0%).
- **Cost.** About 3 seconds per query on the laptop CPU, and a 118 MB model.
- **Setting.** It stays an option (`SMARTARCHIVE_RERANK=1`), recommended where people search in their own words.
  It was measured on the old three-way fusion. Re-ranking on top of the new default (exact + stems) is the next
  measurement.
