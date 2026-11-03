"""Controlled reclassification (`reclass-delta-v1`): when to propose changing a confirmed category.

A confirmed category is a human decision and never changes by itself. New evidence (corrected page text, a
newly trained model, edited categories) produces a new suggestion. A suggestion made after the latest decision
becomes a *reclassification proposal* only when all of these hold:
- it names a different category, above the classifier's own abstention threshold (reason `suggested`);
- the suggested category's share of the scores is at least MIN_CONFIDENCE;
- that share exceeds the confirmed category's share by at least DELTA.

Shares are the suggestion's scores normalized to sum to one, so the rule reads the same for the keyword
baseline (raw keyword scores) and the learned model (probabilities). A person accepts a proposal (a normal
reclassification with a reason) or dismisses it; a dismissal is recorded and that suggestion is not proposed
again. The thresholds were chosen on the development set only (tools/evaluate_synthetic.py reports them).
"""
METHOD = 'reclass-delta-v1'
MIN_CONFIDENCE = 0.6
DELTA = 0.3


def shares(scores: dict[str, float] | None) -> dict[str, float]:
    positive = {k: float(v) for k, v in (scores or {}).items() if v and v > 0}
    total = sum(positive.values())
    return {k: v / total for k, v in positive.items()} if total else {}


def proposal(current: str, suggested: str | None, reason: str, scores: dict[str, float] | None,
             min_confidence: float = MIN_CONFIDENCE, delta: float = DELTA) -> dict | None:
    """The proposal for moving a document confirmed as `current`, or None when the evidence is not strong."""
    if not suggested or suggested == current or reason != 'suggested':
        return None
    share = shares(scores)
    new, old = share.get(suggested, 0.0), share.get(current, 0.0)
    if new < min_confidence or new - old < delta:
        return None
    return {'method': METHOD, 'from_category_id': current, 'to_category_id': suggested,
            'share': round(new, 4), 'current_share': round(old, 4), 'delta': round(new - old, 4),
            'min_confidence': min_confidence, 'min_delta': delta}
