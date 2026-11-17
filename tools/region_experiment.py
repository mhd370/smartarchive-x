r"""Heading and stamp regions (processing/regions.py, regions-v1) against the synthetic ground truth.

  .\.venv\Scripts\python.exe tools/region_experiment.py data\synthetic\corpus_v1 --work results\synthetic_eval\corpus_v1_layout
  .\.venv\Scripts\python.exe tools/region_experiment.py data\synthetic\corpus_v2 --work results\synthetic_eval\corpus_v2_layout

No new OCR: the OCR lines that tools/evaluate_synthetic.py stored for each corpus (latest ready run of each
document, boxes normalized to the original page) are placed on the page images of each original, ruled
tables are found again on that image, and regions.find runs as in the pipeline. The ground truth has a box for
every block. Scores, micro-averaged over pages:
- headings: a predicted heading is correct when at least half of it lies in a ground-truth header or title
  block (precision); a header or title block is found when at least half of it is covered by predicted
  headings (recall);
- stamps: a predicted stamp is correct, and a ground-truth stamp found, when their boxes overlap with
  IoU >= 0.3.
The thresholds of regions.py were set by hand on drawn examples, not tuned on either corpus.
Results: region_experiment.json and .md in the work folder. Synthetic data.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
DPI = 100
MIME = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.tif': 'image/tiff', '.tiff': 'image/tiff'}
LEVELS = ('born_digital', 'clean', 'mild', 'medium', 'severe')


def area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def inter(a, b) -> float:
    return area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def iou(a, b) -> float:
    i = inter(a, b)
    return i / (area(a) + area(b) - i) if i else 0.0


def covered(block, boxes) -> float:
    """Share of `block` covered by the union of `boxes`, on a 50 x 50 grid over the block."""
    import numpy as np
    xs = np.linspace(block[0], block[2], 50)
    ys = np.linspace(block[1], block[3], 50)
    gx, gy = np.meshgrid(xs, ys)
    hit = np.zeros_like(gx, dtype=bool)
    for b in boxes:
        hit |= (gx >= b[0]) & (gx <= b[2]) & (gy >= b[1]) & (gy <= b[3])
    return float(hit.mean())


def score_page(predicted: list[dict], truth: list[dict]) -> dict:
    heads = [r['box'] for r in predicted if r['kind'] == 'heading']
    stamps = [r['box'] for r in predicted if r['kind'] == 'stamp']
    gt_heads = [b['bbox'] for b in truth if b['type'] in ('header', 'title')]
    gt_stamps = [b['bbox'] for b in truth if b['type'] == 'stamp']
    return {
        'heading_predicted': len(heads),
        'heading_correct': sum(1 for h in heads if any(inter(h, g) >= 0.5 * area(h) for g in gt_heads)),
        'heading_truth': len(gt_heads),
        'heading_found': sum(1 for g in gt_heads if covered(g, heads) >= 0.5),
        'stamp_predicted': len(stamps),
        'stamp_correct': sum(1 for s in stamps if any(iou(s, g) >= 0.3 for g in gt_stamps)),
        'stamp_truth': len(gt_stamps),
        'stamp_found': sum(1 for g in gt_stamps if any(iou(s, g) >= 0.3 for s in stamps)),
        'figures': sum(1 for r in predicted if r['kind'] == 'figure'),
    }


def summary(rows: list[dict]) -> dict:
    total = defaultdict(int)
    for row in rows:
        for key, value in row['scores'].items():
            total[key] += value
    rate = lambda a, b: round(total[a] / total[b], 4) if total[b] else None
    return {'pages': len(rows), 'heading_precision': rate('heading_correct', 'heading_predicted'),
            'heading_recall': rate('heading_found', 'heading_truth'),
            'stamp_precision': rate('stamp_correct', 'stamp_predicted'), 'stamp_recall': rate('stamp_found', 'stamp_truth'),
            'stamps_in_truth': total['stamp_truth'], 'figures_per_page': round(total['figures'] / max(1, len(rows)), 2)}


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=0, help='first N documents only (0: all)')
    args = parser.parse_args(argv)
    import numpy as np
    from smartarchive.processing import regions
    from smartarchive.processing.layout import find_tables
    from smartarchive.processing.ocr import Line, Word
    from smartarchive.processing.render import page_images
    corpus, work = args.corpus.resolve(), args.work.resolve()
    manifest = json.loads((corpus / 'manifest.json').read_text(encoding='utf-8'))['documents']
    ids = json.loads((work / 'state.json').read_text(encoding='utf-8'))['ids']
    db = sqlite3.connect(work / 'storage' / 'archive.sqlite3')
    rows = []
    for number, entry in enumerate(manifest[:args.limit or None], 1):
        document_id = ids.get(entry['doc_id'])
        run = db.execute("SELECT id FROM ocr_runs WHERE document_id=? AND status='ready' ORDER BY created_at DESC LIMIT 1",
                         (document_id,)).fetchone() if document_id else None
        if not run:
            continue
        truth = json.loads((corpus / 'ground_truth' / f"{entry['doc_id']}.json").read_text(encoding='utf-8'))
        path = corpus / entry['file']
        for page_no, image, _, _ in page_images(path, MIME[path.suffix.lower()], DPI):
            width, height = image.size
            lines = []
            for text, x0, y0, x1, y1, words in db.execute(
                    'SELECT text, x0, y0, x1, y1, words FROM ocr_lines WHERE run_id=? AND page_no=? ORDER BY line_no',
                    (run[0], page_no)):
                scale = lambda b: tuple(round(v * (width if i % 2 == 0 else height)) for i, v in enumerate(b))
                lines.append(Line(text, None, scale((x0, y0, x1, y1)),
                                  [Word(w['text'], w['confidence'], scale(w['box'])) for w in json.loads(words)]))
            tables = [t.box for t in find_tables(np.asarray(image.convert('L')))]
            found = regions.find(image, lines, tables)
            predicted = [{'kind': r['kind'], 'box': [r['box'][0] / width, r['box'][1] / height, r['box'][2] / width,
                                                     r['box'][3] / height]} for r in found]
            if page_no <= len(truth['pages']):
                rows.append({'doc_id': entry['doc_id'], 'page_no': page_no, 'quality': entry['quality'],
                             'layout': entry['layout'], 'scores': score_page(predicted, truth['pages'][page_no - 1]['blocks'])})
        if number % 100 == 0:
            print(f'  {number}/{len(manifest)} documents', flush=True)
    db.close()
    report = {'corpus': corpus.name, 'synthetic': True, 'method': regions.METHOD, 'all': summary(rows),
              'by_quality': {level: summary([r for r in rows if r['quality'] == level]) for level in LEVELS
                             if any(r['quality'] == level for r in rows)}, 'rows': rows}
    (work / 'region_experiment.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    pct = lambda v: '—' if v is None else f'{v * 100:.1f}%'
    lines = [f"# Regions ({corpus.name}, {len(rows)} pages)", '', 'Synthetic data.', '',
             '| Pages | Heading precision | Heading recall | Stamp precision | Stamp recall | Stamps in truth | Figures/page |',
             '|---|---|---|---|---|---|---|']
    for name, block in [('all', report['all'])] + list(report['by_quality'].items()):
        lines.append(f"| {name} ({block['pages']}) | {pct(block['heading_precision'])} | {pct(block['heading_recall'])} | "
                     f"{pct(block['stamp_precision'])} | {pct(block['stamp_recall'])} | {block['stamps_in_truth']} | "
                     f"{block['figures_per_page']} |")
    (work / 'region_experiment.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
