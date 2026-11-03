"""Learned document classifier (`tfidf-svm-v1`): TF-IDF word uni/bigrams with a calibrated linear SVM.

It is trained on documents whose category a person confirmed, or on a labelled corpus for evaluation, and
replaces the keyword baseline once a model exists. Development set (synthetic corpus_v1, OCR text, 5-fold CV
grouped by document so that copies never straddle folds):
- accuracy 82.9% with no abstention;
- at the 0.4 threshold: coverage 82.9%, precision 96.8%;
- keyword baseline: coverage 78%, precision 90%.

Explanation: the words whose TF-IDF weight times the class coefficient pushed most towards the predicted class.
Abstention: the top probability must reach the threshold (default 0.4). Otherwise the result can still name
the level-1 group when the group's summed probability reaches it (reason `group_only`), or abstain.
The model is a joblib file with a JSON card next to it: classes, examples per class, training time, source.
It never changes a confirmed category; it only suggests.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path

from smartarchive.search.arabic import normalize

METHOD = 'tfidf-svm-v1'
THRESHOLD = 0.4
MIN_PER_CLASS = 3
TOP_TERMS = 6


@dataclass
class Prediction:
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


def _document_text(text: str, filename: str) -> str:
    # The file name is evidence too (people name scans after what they are), as in the keyword baseline.
    return normalize(filename.rsplit('.', 1)[0]) + ' ' + normalize(text)


def train(texts: list[str], filenames: list[str], labels: list[str], source: str,
          threshold: float = THRESHOLD) -> dict:
    """Fit the model. Classes with fewer than MIN_PER_CLASS examples are left out (listed in the card)."""
    from collections import Counter
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import make_pipeline
    from sklearn.svm import LinearSVC
    counts = Counter(labels)
    kept = {label for label, n in counts.items() if n >= MIN_PER_CLASS}
    rows = [(t, f, y) for t, f, y in zip(texts, filenames, labels) if y in kept]
    if len(kept) < 2:
        raise ValueError('at least two categories with %d confirmed documents each are needed' % MIN_PER_CLASS)
    pipeline = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
                             CalibratedClassifierCV(LinearSVC(C=1.0), cv=min(3, min(counts[k] for k in kept))))
    pipeline.fit([_document_text(t, f) for t, f, _ in rows], [y for _, _, y in rows])
    card = {'method': METHOD, 'threshold': threshold, 'source': source,
            'trained_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'classes': sorted(kept), 'examples': {k: counts[k] for k in sorted(kept)},
            'left_out': {k: counts[k] for k in sorted(set(counts) - kept)}}
    return {'pipeline': pipeline, 'card': card}


def save(model: dict, folder: Path) -> Path:
    import joblib
    folder.mkdir(parents=True, exist_ok=True)
    stamp = model['card']['trained_at'].replace(':', '').replace('-', '')
    model['card']['id'] = f'{METHOD}-{stamp}'
    joblib.dump(model['pipeline'], folder / 'classifier.joblib.tmp')
    (folder / 'classifier.joblib.tmp').replace(folder / 'classifier.joblib')
    (folder / 'classifier.json').write_text(json.dumps(model['card'], ensure_ascii=False, indent=1), encoding='utf-8')
    return folder / 'classifier.joblib'


def load(folder: Path) -> dict | None:
    path, card = folder / 'classifier.joblib', folder / 'classifier.json'
    if not (path.is_file() and card.is_file()):
        return None
    import joblib
    return {'pipeline': joblib.load(path), 'card': json.loads(card.read_text(encoding='utf-8'))}


def _explain(pipeline, document: str, label: str) -> list[dict]:
    """Terms with the largest positive contribution (TF-IDF weight x mean SVM coefficient) to `label`."""
    vectorizer, calibrated = pipeline.steps[0][1], pipeline.steps[-1][1]
    vector = vectorizer.transform([document])
    classes = list(calibrated.classes_)
    if label not in classes:
        return []
    import numpy as np
    coefs = []
    for member in calibrated.calibrated_classifiers_:
        svm = member.estimator
        row = classes.index(label) if svm.coef_.shape[0] > 1 else 0
        sign = 1.0 if svm.coef_.shape[0] > 1 or label == classes[1] else -1.0
        coefs.append(sign * svm.coef_[row])
    weights = np.mean(coefs, axis=0)
    indices = vector.nonzero()[1]
    terms = vectorizer.get_feature_names_out()
    scored = sorted(((vector[0, i] * weights[i], terms[i]) for i in indices), reverse=True)
    return [{'keyword': term, 'weight': round(float(value), 4)} for value, term in scored[:TOP_TERMS] if value > 0]


def predict(model: dict, text: str, filename: str, groups: dict[str, str | None], active: set[str]) -> Prediction:
    """Prediction over the model's classes that are still active categories; `groups` maps type → group."""
    pipeline, card = model['pipeline'], model['card']
    if not normalize(text).strip():
        return Prediction(None, None, {}, reason='no_text')
    document = _document_text(text, filename)
    probabilities = dict(zip(pipeline.classes_, pipeline.predict_proba([document])[0]))
    scores = {k: round(float(v), 4) for k, v in probabilities.items() if k in active}
    if not scores:
        return Prediction(None, None, {}, reason='no_keywords')
    top = max(scores, key=scores.get)
    group_scores: dict[str, float] = {}
    for category, value in scores.items():
        if groups.get(category):
            group_scores[groups[category]] = round(group_scores.get(groups[category], 0.0) + value, 4)
    group = max(group_scores, key=group_scores.get) if group_scores else None
    group_confidence = group_scores.get(group) if group else None
    threshold = card.get('threshold', THRESHOLD)
    evidence = {top: _explain(pipeline, document, top)}
    if scores[top] >= threshold:
        return Prediction(top, scores[top], scores, evidence, 'suggested', groups.get(top),
                          group_scores.get(groups.get(top)) if groups.get(top) else None, group_scores)
    if group and group_confidence >= threshold:
        return Prediction(None, scores[top], scores, evidence, 'group_only', group, group_confidence, group_scores)
    return Prediction(None, scores[top], scores, evidence, 'ambiguous', group, group_confidence, group_scores)
