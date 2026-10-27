"""Versioned normalization and deterministic Levenshtein operation counts."""
from dataclasses import asdict, dataclass
import re
import unicodedata

POLICIES = ('strict-v1', 'normalized-v1')
ARABIC_MARKS = re.compile('[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e4\u06e7-\u06e8\u06ea-\u06ed]')


def normalize(text: str, policy: str) -> str:
    """Never mutate raw input; apply the same policy to both sides."""
    if policy not in POLICIES:
        raise ValueError(f'Unknown metric policy: {policy}')
    if policy == 'strict-v1':
        return text
    # Compatibility-fold only Arabic presentation-form blocks, not all Unicode.
    text = ''.join(
        unicodedata.normalize('NFKC', char)
        if '\ufb50' <= char <= '\ufdff' or '\ufe70' <= char <= '\ufeff'
        else char for char in text
    )
    text = unicodedata.normalize('NFC', text)
    text = ARABIC_MARKS.sub('', text).replace('\u0640', '')
    return ' '.join(text.split())


@dataclass(frozen=True)
class Edits:
    substitutions: int = 0
    deletions: int = 0
    insertions: int = 0

    @property
    def distance(self) -> int:
        return self.substitutions + self.deletions + self.insertions


def levenshtein(reference, hypothesis) -> Edits:
    """O(n*m) time/O(m) memory. Ties: substitution, deletion, insertion.

    Operations transform the reference into the hypothesis. Counts from other
    optimal alignments may differ; total distance remains the same.
    """
    previous = [Edits(insertions=j) for j in range(len(hypothesis) + 1)]
    for i, left in enumerate(reference, 1):
        current = [Edits(deletions=i)]
        for j, right in enumerate(hypothesis, 1):
            if left == right:
                current.append(previous[j - 1])
                continue
            diagonal, above, before = previous[j - 1], previous[j], current[j - 1]
            candidates = (
                Edits(diagonal.substitutions + 1, diagonal.deletions, diagonal.insertions),
                Edits(above.substitutions, above.deletions + 1, above.insertions),
                Edits(before.substitutions, before.deletions, before.insertions + 1),
            )
            current.append(min(candidates, key=lambda value: value.distance))
        previous = current
    return previous[-1]


def evaluate(*, reference: str, hypothesis: str, policy: str) -> dict:
    ref, hyp = normalize(reference, policy), normalize(hypothesis, policy)
    result = {'policy': policy, 'reference_evaluated': ref, 'hypothesis_evaluated': hyp}
    for name, left, right in [('cer', ref, hyp), ('wer', ref.split(), hyp.split())]:
        edits = levenshtein(left, right)
        result[name] = {
            **asdict(edits), 'distance': edits.distance,
            'reference_units': len(left), 'hypothesis_units': len(right),
            'rate': edits.distance / len(left) if left else None,
            'rate_status': 'DEFINED' if left else 'UNDEFINED_EMPTY_REFERENCE',
        }
    return result
