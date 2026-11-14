# ADR 0013: Dense retrieval as a fourth ranking

Status: accepted as an optional component, off by default (Sprint 11 / Task 016)

## Context
Ranked search (`hybrid-rrf-v1`, ADR 0009) fuses three lexical rankings:
- exact matches;
- BM25 over light stems;
- character trigrams.

They find a page when it shares words, or pieces of words, with the query. They cannot find a page that
says the same thing in other words, such as «اتفاقية توريد» for «عقد شراء». The brief asks for a dense index
next to the lexical one.

Constraints:
- the archive runs on an ordinary laptop CPU, with no GPU;
- it must keep working when a model is missing;
- vectors are derived data and never replace the text.

## Decision
1. **Model.** multilingual-e5-small, using the Xenova ONNX export with int8-quantized weights (118 MB). It
   runs with ONNX Runtime and the `tokenizers` library, with no PyTorch. `tools/fetch_semantic_model.py`
   downloads it into `models/semantic/multilingual-e5-small`. It records the commit and each file's SHA-256
   in SOURCE.json; the development runs used commit 761b726d.
2. **Vectors.**
   - A page's normalized text is split into windows of 120 words, every 90 words.
   - Each window is embedded with the `passage:` prefix, mean-pooled and L2-normalized.
   - The vectors are stored as float16 in `page_vectors` (migration 8), with a hash of the text.
   - A background indexer embeds pages whose text changed. It is woken after OCR and after a review, and
     runs every minute otherwise. On the development set this took 69 s for 499 pages.
3. **Ranking.**
   - The query is embedded with the `query:` prefix.
   - A page scores as its best window by cosine similarity.
   - Up to 50 pages at or above 0.84 join reciprocal rank fusion as a fourth ranking, so the method becomes
     `hybrid-rrf-v2`.
   - The scan is brute force with numpy. At archive scale (thousands of pages) it is a few milliseconds per
     query; an approximate index can come later.
4. **Optional.** Without the model or its runtime, `GET /api/health` reports `hybrid-rrf-v1` and search
   behaves exactly as before. `SMARTARCHIVE_SEMANTIC=0` turns it off for ablation.

## Choosing the threshold (development set only)
The e5 similarities sit in a narrow, high band:
- relevant pages: p10/p50/p90 = 0.868 / 0.897 / 0.911;
- other top-20 pages: 0.852 / 0.878 / 0.900.

Fused Recall@10 on the 321 development queries, layout-analysis OCR text, computed by `dense_probe.py`
without the file-name signal:

| Dense threshold | All | Subject | Reference number |
|---|---|---|---|
| no dense ranking | 63.9% | 72.8% | 37.8% |
| 0.80 | 63.6% | 74.1% | 32.9% |
| **0.84** | **64.8%** | **74.1%** | **37.8%** |
| 0.88 | 63.9% | 73.2% | 36.6% |
| dense alone | 49.5% | 62.3% | 12.2% |

Dense alone already finds almost as much as exact matching (51.2%). Fused at 0.84 it adds about one point:
1.3 on subject queries and none on reference numbers. Below 0.84, unrelated pages push reference-number hits
out of the top 10.

## Evaluation
`tools/paraphrase_queries.py` rewrites every subject query with fixed synonym rules, for example
«محضر اجتماع لجنة متابعة مشروع X» → «وقائع جلسة الفريق المشرف على X». The rules were written before seeing
any search result. Names stay as written. Recall@10 / MRR@10 from the full evaluator, on layout-analysis OCR
text:

| Queries | Dev lexical | Dev + dense | Test lexical | Test + dense |
|---|---|---|---|---|
| Original (subjects, reference numbers) | 60.9% / 37.6% | 61.8% / 37.8% | 54.9% / 32.5% | 54.5% / 30.1% |
| Paraphrased | 34.1% / 14.5% | **40.8% / 19.0%** | 33.4% / 14.9% | 33.9% / 14.7% |
| Paraphrased, exact mode | 2.1% | — | 3.4% | — |

On the development set, where the threshold was chosen, dense retrieval lifts paraphrased queries by 6.7
points. On the held-out test set the gain shrinks to 0.5 points, and MRR on the original queries falls by
2.4. The development gain does not generalize, so dense retrieval is **off by default**
(`SMARTARCHIVE_SEMANTIC=1` turns it on). The code, the model fetcher and the evaluation stay in place as a
measured negative result.

Likely reasons:
- multilingual-e5-small is small and not Arabic-specific; its similarities sit in a narrow 0.85–0.91 band, so
  one global threshold separates relevant from unrelated pages poorly;
- OCR noise remains in the windows;
- the 0.84 threshold was fitted to a single development set.

What to try next: an Arabic sentence encoder, a cross-encoder re-ranking the fused top 20 instead of a fourth
fused ranking, and a threshold relative to the query's best score instead of an absolute one.

## Consequences
- The paraphrase set shows the real gap: exact search finds 2–3% of paraphrased needs, and the lexical fusion
  finds about a third, mostly through the names that stay the same. Closing that gap remains open work.
- New optional dependencies: onnxruntime and tokenizers (requirements-semantic.txt). The model is 118 MB on
  disk, and embedding a page costs about 0.14 s on the development laptop.
- The model is multilingual and not Arabic-specific. An Arabic sentence encoder could be swapped in behind
  the same `Encoder` interface.
