r"""Classification baselines with macro-F1, the multimodal (text + page image) classifier and folder suggestion.

  .\.venv\Scripts\python.exe tools/classification_experiments.py ^
      --dev data\synthetic\corpus_v1 --dev-work results\synthetic_eval\corpus_v1_layout ^
      --test data\synthetic\corpus_v2 --test-work results\synthetic_eval\corpus_v2_layout --out results\experiments

Uses the OCR text that tools/evaluate_synthetic.py stored for each corpus (no new OCR) and the first page image of
each original file. Everything is trained or chosen on the development corpus (corpus_v1) and measured once on
the held-out test corpus (corpus_v2):
- the three text baselines: keywords-v1, tfidf-svm-v1, tfidf-char-lr-v1 (accuracy, coverage, precision when
  answered, macro-F1, per scan quality);
- visual-layout-v1 alone (classification/visual.py), a logistic regression on page-layout features;
- late fusion: log p_text + beta · log p_image, beta chosen by 5-fold cross-validation on the development set.
  Documents without text get a uniform text distribution, so the image decides; the 0.4 abstention still applies;
- folder suggestion: the department folder of a document predicted from its 5 most similar documents by TF-IDF
  cosine (leave-one-out within the test archive), against the majority folder and the folder most used for the
  document's type.
Results: classification_experiments.json and .md in --out. Synthetic data; report it as such.
"""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))
MIME = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.tif': 'image/tiff', '.tiff': 'image/tiff'}
THRESHOLD = 0.4
BETAS = (0.0, 0.25, 0.5, 1.0, 2.0)


def load(corpus: Path, work: Path, log=print) -> tuple[list[dict], list]:
    from smartarchive.classification import visual
    from smartarchive.classification.classifier import Category
    from smartarchive.processing.render import page_images
    manifest = json.loads((corpus / 'manifest.json').read_text(encoding='utf-8'))['documents']
    ids = json.loads((work / 'state.json').read_text(encoding='utf-8'))['ids']
    db = sqlite3.connect(work / 'storage' / 'archive.sqlite3')
    categories = [Category(r[0], r[1], json.loads(r[2] or '[]'), r[3]) for r in db.execute(
        'SELECT c.id, c.name, c.keywords, m.group_id FROM categories c LEFT JOIN category_group_members m'
        ' ON m.category_id=c.id WHERE c.active=1 ORDER BY c.id')]
    rows = []
    for number, entry in enumerate(manifest, 1):
        document_id = ids.get(entry['doc_id'])
        if not document_id:
            continue
        text = '\n'.join(r[0] for r in db.execute(
            'SELECT text FROM page_texts WHERE document_id=? ORDER BY page_no', (document_id,)))
        path = corpus / entry['file']
        _, image, _, _ = next(page_images(path, MIME[path.suffix.lower()], 72))
        rows.append({'doc_id': entry['doc_id'], 'type': entry['type'], 'quality': entry['quality'],
                     'layout': entry['layout'], 'department': entry['folder'].split('/')[0], 'text': text,
                     'filename': path.name, 'image': visual.features(image)})
        if number % 100 == 0:
            log(f'  {corpus.name}: {number} documents loaded')
    db.close()
    return rows, categories


def text_model(rows, method):
    from smartarchive.classification import learned
    usable = [r for r in rows if r['text'].strip()]
    return learned.train([r['text'] for r in usable], [r['filename'] for r in usable], [r['type'] for r in usable],
                         'experiment', method=method)['pipeline']


def text_probs(pipeline, rows, classes):
    from smartarchive.classification.learned import _document_text
    import numpy as np
    out = np.full((len(rows), len(classes)), 1.0 / len(classes))
    known = [i for i, r in enumerate(rows) if r['text'].strip()]
    if known:
        p = pipeline.predict_proba([_document_text(rows[i]['text'], rows[i]['filename']) for i in known])
        model_classes = list(pipeline.classes_)
        block = np.zeros((len(known), len(classes)))
        for j, c in enumerate(classes):  # a class the model never saw keeps probability 0
            if c in model_classes:
                block[:, j] = p[:, model_classes.index(c)]
        out[known] = block
    return out, set(known)


def image_model(rows):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    import numpy as np
    model = make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=3000))
    model.fit(np.vstack([r['image'] for r in rows]), [r['type'] for r in rows])
    return model


def image_probs(model, rows, classes):
    import numpy as np
    p = model.predict_proba(np.vstack([r['image'] for r in rows]))
    out = np.zeros((len(rows), len(classes)))
    for j, c in enumerate(classes):
        if c in model.classes_:
            out[:, j] = p[:, list(model.classes_).index(c)]
    return out


def fuse(p_text, p_image, beta):
    import numpy as np
    logits = np.log(np.clip(p_text, 1e-6, 1)) + beta * np.log(np.clip(p_image, 1e-6, 1))
    logits -= logits.max(axis=1, keepdims=True)
    p = np.exp(logits)
    return p / p.sum(axis=1, keepdims=True)


def decide(p, classes, has_text=None, text_only=False):
    out = []
    for i, row in enumerate(p):
        if text_only and has_text is not None and i not in has_text:
            out.append(None)  # a text model says nothing about a page without text
            continue
        j = int(row.argmax())
        out.append(classes[j] if row[j] >= THRESHOLD else None)
    return out


def gated(p_text, p_image, beta, classes, has_text):
    """The text model's answer where it gives one; the fused distribution only where it abstains or has no text."""
    text = decide(p_text, classes, has_text, text_only=True)
    fused = decide(fuse(p_text, p_image, beta), classes)
    return [t if t is not None else f for t, f in zip(text, fused)]


def scores(rows, predicted) -> dict:
    from evaluate_synthetic import macro_scores, mean
    items = [{'type': r['type'], 'predicted': p} for r, p in zip(rows, predicted)]
    answered = [i for i in items if i['predicted']]
    block = {'documents': len(items), 'accuracy': mean(1.0 if i['predicted'] == i['type'] else 0.0 for i in items),
             'coverage': mean(1.0 if i['predicted'] else 0.0 for i in items),
             'precision_when_answered': mean(1.0 if i['predicted'] == i['type'] else 0.0 for i in answered),
             'macro_f1': macro_scores(items)['macro_f1'], 'by_quality': {}}
    for level in sorted({r['quality'] for r in rows}):
        sub = [(r, p) for r, p in zip(rows, predicted) if r['quality'] == level]
        block['by_quality'][level] = mean(1.0 if p == r['type'] else 0.0 for r, p in sub)
    return block


def folder_suggestion(rows, predicted_types, k: int = 5) -> dict:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from smartarchive.search.arabic import normalize
    import numpy as np
    texts = [normalize(r['text']) for r in rows]
    matrix = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True).fit_transform(texts)
    similarity = (matrix @ matrix.T).toarray()
    np.fill_diagonal(similarity, -1)
    truth = [r['department'] for r in rows]
    top1 = top3 = majority_hits = type_hits = 0
    for i, row in enumerate(rows):
        others = [j for j in range(len(rows)) if j != i]
        majority = Counter(truth[j] for j in others).most_common(1)[0][0]
        majority_hits += majority == truth[i]
        by_type = Counter(truth[j] for j in others if rows[j]['type'] == predicted_types[i]).most_common(1)
        type_hits += bool(by_type) and by_type[0][0] == truth[i]
        votes = defaultdict(float)
        if texts[i].strip():
            for j in np.argsort(-similarity[i])[:k]:
                if similarity[i, j] > 0:
                    votes[truth[j]] += float(similarity[i, j])
        ranked = [name for name, _ in sorted(votes.items(), key=lambda item: -item[1])] or [majority]
        top1 += ranked[0] == truth[i]
        top3 += truth[i] in ranked[:3]
    n = len(rows)
    return {'documents': n, 'departments': len(set(truth)), 'knn_top1': round(top1 / n, 4),
            'knn_top3': round(top3 / n, 4), 'majority_folder': round(majority_hits / n, 4),
            'folder_of_predicted_type': round(type_hits / n, 4), 'k': k}


def markdown(report: dict) -> str:
    pct = lambda v: '—' if v is None else f'{v * 100:.1f}%'
    levels = sorted(next(iter(report['test'].values()))['by_quality'])
    lines = ['# Classification experiments (synthetic data)', '',
             f"Trained and chosen on {report['dev_corpus']}, measured on {report['test_corpus']} "
             f"({report['test_documents']} documents). Fusion beta chosen by 5-fold CV on the development set: "
             f"{report['beta']}.", '',
             '| Model | Accuracy | Coverage | Precision when answered | Macro-F1 | ' + ' | '.join(levels) + ' |',
             '|---|---|---|---|---|' + '---|' * len(levels)]
    for name, b in report['test'].items():
        lines.append(f"| {name} | {pct(b['accuracy'])} | {pct(b['coverage'])} | {pct(b['precision_when_answered'])} | "
                     f"{pct(b['macro_f1'])} | " + ' | '.join(pct(b['by_quality'][q]) for q in levels) + ' |')
    lines += ['', '## Development set, 5-fold cross-validation (fusion beta)', '',
              '| beta | Fusion accuracy | Gated accuracy |', '|---|---|---|']
    lines += [f"| {b} | {pct(a)} | {pct(report['gate_beta_cv'][b])} |" for b, a in report['beta_cv'].items()]
    f = report['folders']
    lines += ['', '## Folder suggestion (department, test set, leave-one-out)', '',
              f"{f['documents']} documents, {f['departments']} departments.", '',
              '| Method | Accuracy |', '|---|---|',
              f"| majority folder | {pct(f['majority_folder'])} |",
              f"| folder most used for the predicted type | {pct(f['folder_of_predicted_type'])} |",
              f"| {f['k']} most similar documents (TF-IDF), top 1 | {pct(f['knn_top1'])} |",
              f"| same, correct folder among top 3 | {pct(f['knn_top3'])} |"]
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dev', type=Path, required=True)
    parser.add_argument('--dev-work', type=Path, required=True)
    parser.add_argument('--test', type=Path, required=True)
    parser.add_argument('--test-work', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'results' / 'experiments')
    args = parser.parse_args(argv)
    import numpy as np
    from sklearn.model_selection import StratifiedKFold
    from smartarchive.classification.classifier import classify
    from smartarchive.classification.learned import CHAR_METHOD, METHOD
    started = time.time()
    dev, _ = load(args.dev.resolve(), args.dev_work.resolve())
    test, categories = load(args.test.resolve(), args.test_work.resolve())
    classes = sorted({r['type'] for r in dev})
    print(f'loaded {len(dev)} + {len(test)} documents ({time.time() - started:.0f}s)', flush=True)

    # beta by 5-fold CV on the development set (out-of-fold text and image probabilities)
    folds = StratifiedKFold(5, shuffle=True, random_state=2026)
    oof_text, oof_image = np.zeros((len(dev), len(classes))), np.zeros((len(dev), len(classes)))
    labels = [r['type'] for r in dev]
    for train_index, held_index in folds.split(np.zeros(len(dev)), labels):
        train_rows, held_rows = [dev[i] for i in train_index], [dev[i] for i in held_index]
        oof_text[held_index] = text_probs(text_model(train_rows, METHOD), held_rows, classes)[0]
        oof_image[held_index] = image_probs(image_model(train_rows), held_rows, classes)
    dev_text = {i for i, r in enumerate(dev) if r['text'].strip()}
    beta_cv, gate_cv = {}, {}
    for beta in BETAS:
        predicted = decide(fuse(oof_text, oof_image, beta), classes)
        beta_cv[beta] = round(sum(p == y for p, y in zip(predicted, labels)) / len(labels), 4)
        predicted = gated(oof_text, oof_image, beta, classes, dev_text)
        gate_cv[beta] = round(sum(p == y for p, y in zip(predicted, labels)) / len(labels), 4)
    beta = max(BETAS, key=lambda b: (beta_cv[b], -b))
    gate_beta = max(BETAS, key=lambda b: (gate_cv[b], -b))
    print(f'beta CV {beta_cv} -> {beta}; gated {gate_cv} -> {gate_beta}', flush=True)

    results = {}
    results['keywords-v1'] = scores(test, [classify(r['text'], r['filename'], categories).category_id for r in test])
    p_svm, has_text = text_probs(text_model(dev, METHOD), test, classes)
    results['tfidf-svm-v1'] = scores(test, decide(p_svm, classes, has_text, text_only=True))
    p_char, _ = text_probs(text_model(dev, CHAR_METHOD), test, classes)
    results['tfidf-char-lr-v1'] = scores(test, decide(p_char, classes, has_text, text_only=True))
    p_image = image_probs(image_model(dev), test, classes)
    results['visual-layout-v1 (image only)'] = scores(test, decide(p_image, classes))
    results[f'tfidf-svm-v1 + visual-layout-v1 (beta={beta:g})'] = scores(test, decide(fuse(p_svm, p_image, beta), classes))
    results[f'gated: tfidf-svm-v1, else fusion (beta={gate_beta:g})'] = scores(
        test, gated(p_svm, p_image, gate_beta, classes, has_text))
    if beta != 1.0:
        results['tfidf-svm-v1 + visual-layout-v1 (beta=1, not chosen)'] = scores(test, decide(fuse(p_svm, p_image, 1.0), classes))
    svm_types = [classes[int(row.argmax())] for row in p_svm]
    report = {'synthetic': True, 'dev_corpus': args.dev.name, 'test_corpus': args.test.name,
              'dev_documents': len(dev), 'test_documents': len(test), 'beta': beta,
              'beta_cv': {str(k): v for k, v in beta_cv.items()},
              'gate_beta': gate_beta, 'gate_beta_cv': {str(k): v for k, v in gate_cv.items()}, 'test': results,
              'folders': folder_suggestion(test, svm_types)}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'classification_experiments.json').write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                                             encoding='utf-8')
    (args.out / 'classification_experiments.md').write_text(markdown(report), encoding='utf-8')
    print(markdown(report))
    print(f'done in {time.time() - started:.0f}s')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
