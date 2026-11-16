# Literature review (working draft)

Status: draft for the thesis and paper, Sprint 12. 51 works in 8 themes, each with what it contributes and
where SmartArchive-X stands relative to it. Every entry was checked against the publisher or an index (DBLP, ACL Anthology, arXiv, Springer).
The paper draft cites them with these numbers.

## 1. Arabic OCR

1. **R. Smith (2007). An overview of the Tesseract OCR engine.** ICDAR 2007. The architecture of the engine
   we use: adaptive classification, line finding, and later an LSTM recognizer (4.x+).
   - *Relation:* our only production engine. Section 6 of docs/synthetic_evaluation.md shows why it stayed.
2. **S. Faizullah, M. S. Ayub, S. Hussain, M. A. Khan (2023). A survey of OCR in Arabic language:
   applications, techniques, and challenges.** Applied Sciences 13(7):4584. A survey of Arabic OCR: cursive
   joining, dots and diacritics, ligatures, datasets.
   - *Relation:* motivates the normalization layer and the per-level evaluation.
3. **R. Najam, S. Faizullah (2023). Analysis of recent deep learning techniques for Arabic handwritten-text
   OCR and post-OCR correction.** Applied Sciences 13(13):7568, doi:10.3390/app13137568.
   - *Relation:* post-OCR correction is the open route for our digit errors.
4. **A. Heakl, A. Sohail, M. Ranjan, et al. (2025). KITAB-Bench: a comprehensive multi-domain benchmark for
   Arabic OCR and document understanding.** Findings of ACL 2025, arXiv:2502.14949.
   - 8,809 samples across 9 domains and 36 sub-domains.
   - Vision-language models (GPT-4o, Gemini, Qwen) beat traditional OCR tools (EasyOCR, PaddleOCR, Surya) by
     about 60% in CER.
   - The best PDF-to-Markdown result reaches only about 65% accuracy.
   - *Relation:* the closest benchmark to our setting. Our engine probe agrees that the classical engines
     differ sharply by document type.
5. **S. A. Mahmoud et al. (2014). KHATT: an open Arabic offline handwritten text database.** Pattern
   Recognition 47(3). The standard handwritten Arabic dataset.
   - *Relation:* handwriting is out of our scope (printed institutional documents); cited to bound it.
6. **Y. Du et al. (2020). PP-OCR: a practical ultra lightweight OCR system.** arXiv:2009.09941, the PaddleOCR
   family.
   - *Relation:* evaluated as a second engine. Worse on our scans (CER 40.9% against 30.8%).
7. **M. Li et al. (2023). TrOCR: transformer-based optical character recognition with pre-trained models.**
   AAAI 2023. An end-to-end transformer recognizer.
   - *Relation:* the class of model that could fix Arabic-Indic digit confusions once fine-tuned. Future work.
8. **BADAM: a public dataset for baseline detection in Arabic-script manuscripts (2019).** arXiv:1907.04041.
   - *Relation:* layout for Arabic manuscripts; contrasts with our ruled administrative tables.

## 2. OCR noise and its effect on downstream tasks

9. **K. Taghva, J. Borsack, A. Condit (1994). The effects of noisy data on text retrieval.** JASIS 45(1):50–58.
   Retrieval on OCR text stays usable for long documents but degrades for short ones and for exact terms.
   - *Relation:* our reference-number queries are this case: short and exact. Exact search finds 7–9% of them.
10. **K. Taghva et al. (1996). Evaluation of model-based retrieval effectiveness with OCR text.** ACM TOIS
    14(1).
    - *Relation:* the same question for ranked models, which motivates measuring both modes.
11. **D. Lopresti (2009). Optical character recognition errors and their effects on natural language
    processing.** IJDAR 12(3). Errors cascade from OCR into tokenization, tagging and so on, and should be
    measured at each stage.
    - *Relation:* our evaluator reports OCR, metadata, classification, relations and search on the same
      documents for this reason.
12. **P. McNamee, J. Mayfield (2004). Character n-gram tokenization for European language text retrieval.**
    Information Retrieval 7(1–2):73–97. Overlapping character n-grams match or beat stemming, without any
    language resources, and are robust to spelling variation.
    - *Relation:* the basis of our trigram index. Our ablation (Sprint 12) found that on these corpora it does
      not add to the word index, so it is now opt-in.

## 3. Arabic text processing for retrieval

13. **L. S. Larkey, L. Ballesteros, M. E. Connell (2002/2007). Improving stemming for Arabic information
    retrieval: light stemming and co-occurrence analysis.** SIGIR 2002, and a chapter in *Arabic
    Computational Morphology* (Springer, 2007). Light10 removes prefixes and suffixes without full
    morphological analysis, and beats root stemming for retrieval.
    - *Relation:* our `stem()` follows the light-stemming idea.
14. **W. Antoun, F. Baly, H. Hajj (2020). AraBERT: transformer-based model for Arabic language
    understanding.** OSACT 2020.
    - *Relation:* a candidate for the third classification baseline and for an Arabic re-ranker.
15. **G. Inoue et al. (2021). The interplay of variant, size, and task type in Arabic pre-trained language
    models (CAMeLBERT).** WANLP 2021.
    - *Relation:* as above. It covers MSA versus dialect variants; our documents are MSA.
16. **N. Habash (2010). Introduction to Arabic natural language processing.** Morgan & Claypool.
    - *Relation:* the reference for orthographic normalization (hamza, alef maqsura, taa marbuta) that our
      `normalize()` applies.

## 4. Ranking and retrieval

17. **S. Robertson, H. Zaragoza (2009). The probabilistic relevance framework: BM25 and beyond.** Foundations
    and Trends in IR 3(4).
    - *Relation:* the scoring of both of our FTS5 indexes.
18. **G. V. Cormack, C. L. A. Clarke, S. Büttcher (2009). Reciprocal rank fusion outperforms Condorcet and
    individual rank learning methods.** SIGIR 2009. A simple fusion, 1/(k+rank) with k=60, beats learned
    fusion.
    - *Relation:* exactly our fusion (`hybrid-rrf-v1/v2`, k=60).
19. **V. Karpukhin et al. (2020). Dense passage retrieval for open-domain question answering.** EMNLP 2020.
    - *Relation:* the dense retrieval paradigm; ADR 0013.
20. **L. Wang et al. (2024). Multilingual E5 text embeddings: a technical report.** arXiv:2402.05672.
    - *Relation:* our dense model (multilingual-e5-small, ONNX int8).
21. **R. Nogueira, K. Cho (2019). Passage re-ranking with BERT.** arXiv:1901.04085. A cross-encoder
    re-ranker.
    - *Relation:* the brief's "AI re-ranking". Next sprint.
22. **O. Khattab, M. Zaharia (2020). ColBERT: efficient and effective passage search via contextualized late
    interaction.** SIGIR 2020.
    - *Relation:* a middle ground between dense and cross-encoder. Discussed, not adopted (index size on a
      laptop).
23. **N. Thakur et al. (2021). BEIR: a heterogeneous benchmark for zero-shot evaluation of information
    retrieval models.** NeurIPS Datasets & Benchmarks. BM25 remains a strong zero-shot baseline, and dense
    models often fail to beat it out of domain.
    - *Relation:* matches our finding. Dense adds about 1 point over the lexical fusion on our queries.
24. **J. Lin et al. (2021). Pyserini: a Python toolkit for reproducible information retrieval research.**
    SIGIR 2021.
    - *Relation:* a reproducibility standard. Our evaluator pins corpora, seeds and methods for the same
      reason.

## 5. Document layout analysis and tables

25. **X. Zhong, J. Tang, A. Jimeno Yepes (2019). PubLayNet: largest dataset ever for document layout
    analysis.** ICDAR 2019.
    - *Relation:* learned layout detection. We use rule-based ruling-line detection instead, because no
      Arabic administrative layout set exists.
26. **M. Li et al. (2020). DocBank: a benchmark dataset for document layout analysis.** COLING 2020.
27. **M. Göbel et al. (2013). ICDAR 2013 table competition.** ICDAR 2013.
    - *Relation:* table detection and structure recognition as separate tasks. Our `layout-v1` does both,
      for ruled tables only.
28. **S. Schreiber et al. (2017). DeepDeSRT: deep learning for detection and structure recognition of tables
    in document images.** ICDAR 2017.
29. **B. Smock, R. Pesala, R. Abraham (2022). PubTables-1M: towards comprehensive table extraction from
    unstructured documents.** CVPR 2022 (Table Transformer).
    - *Relation:* the learned alternative for unruled tables, a limitation stated in ADR 0012.
30. **T. M. Breuel (2002). Two geometric algorithms for layout analysis.** DAS 2002. Whitespace-cover
    column finding.
    - *Relation:* the same principle as our gutter detection, though our version is simpler.
31. **N. Otsu (1979). A threshold selection method from gray-level histograms.** IEEE SMC 9(1).
    - *Relation:* used for ink masks in quality assessment and layout.

## 6. Document understanding and classification

32. **A. W. Harley, A. Ufkes, K. G. Derpanis (2015). Evaluation of deep convolutional nets for document image
    classification and retrieval (RVL-CDIP).** ICDAR 2015.
    - *Relation:* image-based document classification, the basis of the planned multimodal classifier for
      severe scans.
33. **Y. Xu et al. (2020). LayoutLM: pre-training of text and layout for document image understanding.**
    KDD 2020.
34. **Y. Huang et al. (2022). LayoutLMv3: pre-training for document AI with unified text and image masking.**
    ACM MM 2022.
    - *Relation:* the multimodal state of the art. It is English-centred; Arabic needs either a multilingual
      variant (LayoutXLM) or fine-tuning.
35. **G. Kim et al. (2022). OCR-free document understanding transformer (Donut).** ECCV 2022. It also
    introduces SynthDoG, synthetic document generation for pre-training.
    - *Relation:* supports our use of a synthetic corpus with known ground truth (ADR 0008).
36. **G. Jaume, H. K. Ekenel, J.-P. Thiran (2019). FUNSD: a dataset for form understanding in noisy scanned
    documents.** ICDAR-OST 2019.
    - *Relation:* key–value extraction. Our metadata extraction (rules-v2) is the rule-based counterpart.
37. **T. Joachims (1998). Text categorization with support vector machines.** ECML 1998.
    - *Relation:* the method behind `tfidf-svm-v1`.
38. **F. Sebastiani (2002). Machine learning in automated text categorization.** ACM Computing Surveys 34(1).

## 7. Trustworthy predictions: calibration, abstention, human review

39. **J. Platt (1999). Probabilistic outputs for support vector machines.** In *Advances in Large Margin
    Classifiers*.
    - *Relation:* the calibration (`CalibratedClassifierCV`) that turns SVM scores into the probabilities our
      abstention and reclassification thresholds use.
40. **C. Guo et al. (2017). On calibration of modern neural networks.** ICML 2017.
41. **Y. Geifman, R. El-Yaniv (2017). Selective classification for deep neural networks.** NeurIPS 2017.
    The risk–coverage trade-off.
    - *Relation:* our reports give coverage and precision when answered (for example 82.7% / 98.0%), which is
      a risk–coverage point.

## 8. Duplicates, records management

42. **A. Z. Broder (1997). On the resemblance and containment of documents.** Compression and Complexity of
    Sequences, and **M. S. Charikar (2002). Similarity estimation techniques from rounding algorithms**
    (SimHash), STOC 2002.
    - *Relation:* near-duplicate detection. Our fingerprint-v2 uses exact hashes plus identifying fields; a
      MinHash route would scale it.
- **ISO 15489-1:2016. Information and documentation — Records management.** The principles our design
  follows: an immutable original, metadata, an audit trail, controlled classification and access.
- **[50] State Archives and Records Authority of New South Wales (2018). Case study – internal pilot –
  machine learning and records management** (Future Proof blog, 20 March 2018) and the **external pilot**
  case study (24 September 2018). Machine-learning pilots for classifying government records, with
  records staff checking the results.
  - *Relation:* the same suggest–confirm pattern as our design; these pilots publish no open evaluation.
- **[51]** ISO 15489-1:2016 above.

## Comparison with SmartArchive-X

| Work / system | Arabic | Scans | Layout | Classification | Search | Human review | Open evaluation |
|---|---|---|---|---|---|---|---|
| Tesseract (1) | yes | yes | psm 3 | — | — | — | — |
| KITAB-Bench (4) | yes | yes | yes (task) | — | — | — | benchmark |
| PubLayNet/DocBank (25–26) | no | partly | learned | — | — | — | yes |
| LayoutLMv3 (34) | no (EN) | yes | yes | learned multimodal | — | — | yes |
| BEIR / dense IR (19–23) | partly | no | — | — | yes | — | yes |
| Records ML pilots (grey) | no | mixed | — | learned | — | yes | no |
| **SmartArchive-X** | **yes** | **yes** | **ruled tables, two columns** | **keywords + calibrated SVM, abstention, reclassification** | **exact + BM25 + trigrams + dense, RRF** | **yes (review, confirm, audit)** | **synthetic dev/test split, all stages** |

**Gap this project addresses.** Several pieces of work are strong on their own:
- Arabic OCR benchmarks (4) evaluate recognition;
- document-AI models (33–35) are English-centred and evaluated on a single task;
- records-management pilots are not evaluated openly.

None combines the whole archive workflow for Arabic administrative documents, with each stage measured on the
same held-out documents and a person kept in control of every decision.

## 9. Arabic OCR correction and retrieval on OCR text (added in Sprint 12)
44. **W. Magdy, K. Darwish (2006). Arabic OCR error correction using character segment correction, language
    modeling, and shallow morphology.** EMNLP 2006, pp. 408–414. A noisy-channel model over character
    segments with a trigram language model; segment-level correction beats single-character correction.
    - *Relation:* the post-OCR route for our digit and letter confusions.
45. **W. Magdy, K. Darwish (2008). Effect of OCR error correction on Arabic retrieval.** Information Retrieval
    11:405–425. Correction helps retrieval only when it removes many errors; short character n-grams are a
    strong index unit without correction.
    - *Relation:* motivated our trigram ranking. On our synthetic corpora the word-level BM25 index carried the
      gain instead (ADR 0014), a difference worth testing on real scans, whose errors differ from ours.
46. **I. Kissos, N. Dershowitz (2016). OCR error correction using character correction and feature-based word
    classification.** arXiv:1604.06225. Candidates from a learned confusion matrix, chosen by a regression
    over language-model and OCR features; word error rate 30% → 21% on printed Arabic archive documents.
    - *Relation:* the closest setting to ours (printed Arabic institutional pages).
47. **M. S. Kasem, M. Mahmoud, H.-S. Kang (2023). Advancements and challenges in Arabic optical character
    recognition: a comprehensive survey.** arXiv:2312.11812.
    - *Relation:* recent survey of datasets, preprocessing and post-processing for Arabic OCR.
48. **L. Bonifacio et al. (2021). mMARCO: a multilingual version of the MS MARCO passage ranking dataset.**
    arXiv:2108.13897. MS MARCO machine-translated into more than ten languages, Arabic among them.
    - *Relation:* the training data of our cross-encoder re-ranker.
49. **W. Wang et al. (2021). MiniLMv2: multi-head self-attention relation distillation for compressing
    pretrained transformers.** Findings of ACL 2021.
    - *Relation:* the multilingual MiniLM architecture of the re-ranker (12 layers, hidden size 384).

## Evaluation methodology
43. **K. Järvelin, J. Kekäläinen (2002). Cumulated gain-based evaluation of IR techniques.** ACM TOIS 20(4),
    doi:10.1145/582415.582418.
    - *Relation:* our nDCG@10.

## Still to do
- The related-work section of the paper draft uses this list; keep the numbers in step when adding works.
