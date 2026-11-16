# ADR 0014: Search ablation, confidence-aware fusion and cross-encoder re-ranking

Status: accepted (Sprint 12 / Task 017)

## Context
The brief asks for three things the lexical fusion of ADR 0009 did not yet have:
- AI re-ranking of the results;
- an index that knows how reliable the OCR text is;
- an ablation that shows what each part of the search contributes.

Ranked search (`hybrid-rrf-v1`) fuses three page rankings:
- exact matches (every query word, whole phrase first);
- BM25 over light stems;
- BM25 over character trigrams.

ADR 0013 added an optional dense ranking. It did not generalize from the development set to the test set.

## Decision
1. **Ablation.** `ranked.search(..., components=...)` restricts the fusion to any subset of the rankings.
   `tools/search_experiments.py` runs all seven subsets of the three lexical rankings on an evaluated corpus,
   through the same document-level search as the API (`PageTexts.search_ranked`).
2. **Confidence-aware fusion.** `ranked.page_confidence` reads each page's mean OCR word confidence c (0–1)
   from `page_analyses`; reviewed pages count as c = 1. With a weight α > 0:
   - the exact ranking's contribution is multiplied by 1 − α(1 − c);
   - the trigram ranking's contribution is multiplied by 1 + α(1 − c).

   The reason: a badly read page rarely holds the query's exact words, but its misread words still share
   trigrams with them. `SMARTARCHIVE_CONFIDENCE_ALPHA` sets α. The default is set from the measurements below.
3. **Cross-encoder re-ranking** (`search/rerank.py`, `ce-mminilm-v1`).
   - **Model:** cross-encoder/mmarco-mMiniLMv2-L12-H384-v1, a multilingual MiniLM trained on mMARCO
     (MS MARCO machine-translated, Arabic included). It runs as int8 ONNX on the CPU.
     `tools/fetch_reranker_model.py` downloads it hash-checked into `models/reranker/mmarco-mMiniLMv2-L12`.
   - **Input:** for each of the top 20 documents, a 700-character window of its best page around the first
     matched word.
   - **`replace` mode:** the cross-encoder score alone re-orders the 20.
   - **`fuse` mode:** reciprocal rank fusion of the hybrid rank and the cross-encoder rank, so a confident
     lexical match is not thrown away when the model misreads OCR noise.
   - **Enabling:** `SMARTARCHIVE_RERANK=1` turns it on when the model is present, and
     `SMARTARCHIVE_RERANK_MODE` chooses the mode. The health endpoint reports the full method, for example
     `hybrid-rrf-v3+ce-mminilm-v1`.
4. **New default fusion: exact + BM25 stems (`hybrid-rrf-v3`).** The ablation showed that dropping the trigram
   ranking raises Recall@10 and MRR on the development set, the reference-number queries included, and the test
   set confirmed it. The trigram index is still built and can be fused again with
   `SMARTARCHIVE_SEARCH_COMPONENTS=exact,words,grams` (the earlier `hybrid-rrf-v1`); the method name in
   `/api/health` and in search results says which fusion ran.
5. **Choosing settings.** α and the re-ranking mode are chosen on the development set by nDCG@10 over the
   original queries (`--choose-from`). The test set is run once with those choices.

## Results
See "Sprint 12" in docs/synthetic_evaluation.md.

## Consequences
- Re-ranking costs one model call per query over 20 passages. It is optional, and without the model or its
  runtime the search is unchanged.
- The ablation, confidence weights and re-ranking all run on stored OCR text, so they can be repeated in
  minutes without new OCR.
