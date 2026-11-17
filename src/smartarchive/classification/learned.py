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

Multimodal (ADR 0015, wired in Sprint 13): when first-page layout features (visual.py) are available for enough
confirmed documents, a second model is trained on them and saved next to the text model. A suggestion then fuses
the two by log p = log p_text + BETA · log p_image (BETA = 1, chosen by cross-validation on the development set);
a page without text gets a uniform text distribution, so its image decides. The method is recorded as
`tfidf-svm-v1+visual-layout-v1`.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path

from smartarchive.search.arabic import normalize

METHOD = 'tfidf-svm-v1'
CHAR_METHOD = 'tfidf-char-lr-v1'  # third baseline: character 2–5-grams, logistic regression (ADR 0010 addendum)
METHODS = (METHOD, CHAR_METHOD)
THRESHOLD = 0.4
BETA = 1.0
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
    image_used: bool = False

    @property
    def candidates(self) -> list[tuple[str, float]]:
        return sorted(((k, v) for k, v in self.scores.items() if v > 0), key=lambda item: -item[1])


def _document_text(text: str, filename: str) -> str:
    # The file name is evidence too (people name scans after what they are), as in the keyword baseline.
    return normalize(filename.rsplit('.', 1)[0]) + ' ' + normalize(text)


def train(texts: list[str], filenames: list[str], labels: list[str], source: str,
          threshold: float = THRESHOLD, method: str = METHOD, images: list | None = None) -> dict:
    """Fit the model. Classes with fewer than MIN_PER_CLASS examples are left out (listed in the card).
    `images`: first-page layout features per document (None where unknown); with enough of them an image model
    is trained too (multimodal fusion)."""
    from collections import Counter
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.svm import LinearSVC
    if method not in METHODS:
        raise ValueError(f'unknown method {method}')
    counts = Counter(labels)
    kept = {label for label, n in counts.items() if n >= MIN_PER_CLASS}
    rows = [(t, f, y) for t, f, y in zip(texts, filenames, labels) if y in kept]
    if len(kept) < 2:
        raise ValueError('at least two categories with %d confirmed documents each are needed' % MIN_PER_CLASS)
    folds = min(3, min(counts[k] for k in kept))
    if method == CHAR_METHOD:  # robust to OCR-split words; calibrated the same way so explanations work alike
        pipeline = make_pipeline(TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 5), min_df=2, sublinear_tf=True,
                                                 max_features=200_000),
                                 CalibratedClassifierCV(LogisticRegression(C=10, max_iter=2000), cv=folds))
    else:
        pipeline = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
                                 CalibratedClassifierCV(LinearSVC(C=1.0), cv=folds))
    pipeline.fit([_document_text(t, f) for t, f, _ in rows], [y for _, _, y in rows])
    card = {'method': method, 'threshold': threshold, 'source': source,
            'trained_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'classes': sorted(kept), 'examples': {k: counts[k] for k in sorted(kept)},
            'left_out': {k: counts[k] for k in sorted(set(counts) - kept)}}
    image = train_image(images, labels) if images else None
    if image:
        card.update({'image_method': image['method'], 'beta': BETA, 'image_examples': image['examples']})
    return {'pipeline': pipeline, 'card': card, 'image': image['pipeline'] if image else None}


def train_image(images: list, labels: list[str]) -> dict | None:
    """Standardized logistic regression on page-layout features; None without two classes of MIN_PER_CLASS."""
    from collections import Counter
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from .visual import METHOD as IMAGE_METHOD
    pairs = [(x, y) for x, y in zip(images, labels) if x is not None]
    counts = Counter(y for _, y in pairs)
    kept = {label for label, n in counts.items() if n >= MIN_PER_CLASS}
    pairs = [(x, y) for x, y in pairs if y in kept]
    if len(kept) < 2:
        return None
    pipeline = make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=3000))
    pipeline.fit(np.vstack([x for x, _ in pairs]), [y for _, y in pairs])
    return {'pipeline': pipeline, 'method': IMAGE_METHOD, 'examples': {k: counts[k] for k in sorted(kept)}}


def method_name(model: dict, image_used: bool) -> str:
    method = model['card'].get('method', METHOD)
    return f"{method}+{model['card']['image_method']}" if image_used else method


def save(model: dict, folder: Path) -> Path:
    import joblib
    folder.mkdir(parents=True, exist_ok=True)
    stamp = model['card']['trained_at'].replace(':', '').replace('-', '')
    model['card']['id'] = f"{model['card'].get('method', METHOD)}-{stamp}"
    joblib.dump(model['pipeline'], folder / 'classifier.joblib.tmp')
    (folder / 'classifier.joblib.tmp').replace(folder / 'classifier.joblib')
    if model.get('image') is not None:
        joblib.dump(model['image'], folder / 'classifier_image.joblib.tmp')
        (folder / 'classifier_image.joblib.tmp').replace(folder / 'classifier_image.joblib')
    elif (folder / 'classifier_image.joblib').is_file():
        (folder / 'classifier_image.joblib').unlink()  # never fuse with an image model from an older training
    (folder / 'classifier.json').write_text(json.dumps(model['card'], ensure_ascii=False, indent=1), encoding='utf-8')
    return folder / 'classifier.joblib'


def load(folder: Path) -> dict | None:
    path, card = folder / 'classifier.joblib', folder / 'classifier.json'
    if not (path.is_file() and card.is_file()):
        return None
    import joblib
    card = json.loads(card.read_text(encoding='utf-8'))
    image_path = folder / 'classifier_image.joblib'
    image = joblib.load(image_path) if card.get('image_method') and image_path.is_file() else None
    return {'pipeline': joblib.load(path), 'card': card, 'image': image}


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


def predict(model: dict, text: str, filename: str, groups: dict[str, str | None], active: set[str],
            image=None) -> Prediction:
    """Prediction over the model's classes that are still active categories; `groups` maps type → group.
    `image`: the document's first-page layout features, fused with the text when the model has an image part."""
    import numpy as np
    pipeline, card = model['pipeline'], model['card']
    has_text = bool(normalize(text).strip())
    image_model = model.get('image') if image is not None else None
    if not has_text and image_model is None:
        return Prediction(None, None, {}, reason='no_text')
    document = _document_text(text, filename)
    classes = list(pipeline.classes_)
    p_text = pipeline.predict_proba([document])[0] if has_text else np.full(len(classes), 1 / len(classes))
    if image_model is not None:
        given = image_model.predict_proba(np.asarray(image, dtype=np.float64).reshape(1, -1))[0]
        lookup = dict(zip(image_model.classes_, given))
        p_image = np.array([lookup.get(c, 0.0) for c in classes])
        logits = np.log(np.clip(p_text, 1e-6, 1)) + card.get('beta', BETA) * np.log(np.clip(p_image, 1e-6, 1))
        p = np.exp(logits - logits.max())
        p_text = p / p.sum()
    probabilities = dict(zip(classes, p_text))
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
    evidence = {top: _explain(pipeline, document, top)} if has_text else {top: []}
    used = image_model is not None
    if scores[top] >= threshold:
        return Prediction(top, scores[top], scores, evidence, 'suggested', groups.get(top),
                          group_scores.get(groups.get(top)) if groups.get(top) else None, group_scores, used)
    if group and group_confidence >= threshold:
        return Prediction(None, scores[top], scores, evidence, 'group_only', group, group_confidence, group_scores,
                          used)
    return Prediction(None, scores[top], scores, evidence, 'ambiguous', group, group_confidence, group_scores, used)
