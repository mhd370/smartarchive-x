r"""Compare OCR engines on the synthetic development set, with the archive's own preprocessing.

  .venv-ocr\Scripts\python.exe tools/ocr_engine_probe.py data\synthetic\corpus_v1 --per-level 8 [--engines paddle,easyocr,tesseract]

Run in a separate environment (`.venv-ocr`), so trying heavy engines never changes the archive's own
dependencies. For every sampled page, the probe applies the same quality assessment and preprocessing as the
pipeline, then measures CER/WER (policy normalized-v1) and a digit-only CER. Line order is reconstructed as
top to bottom, right to left. Engines that return Arabic lines in visual order are also scored with each line
reversed, and the better orientation is reported. Results go to results/ocr_probe/<stamp>.json and .md.
Development set only: never run it on the test set.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')


def reading_order(items: list[tuple[tuple[float, float, float, float], str]]) -> list[str]:
    """Group boxes (x0, y0, x1, y1) into rows by vertical overlap, rows top to bottom, boxes right to left."""
    if not items:
        return []
    heights = sorted(b[3] - b[1] for b, _ in items)
    tolerance = max(4.0, heights[len(heights) // 2] * 0.5)
    rows: list[list] = []
    for box, text in sorted(items, key=lambda item: (item[0][1] + item[0][3]) / 2):
        centre = (box[1] + box[3]) / 2
        if rows and abs(rows[-1][0] - centre) <= tolerance:
            rows[-1][1].append((box, text))
            rows[-1][0] = (rows[-1][0] + centre) / 2
        else:
            rows.append([centre, [(box, text)]])
    return [' '.join(text for _, text in sorted(row, key=lambda item: -item[0][2])) for _, row in rows]


class Tesseract:
    name = 'tesseract'

    def __init__(self, languages: str, tessdata: Path | None):
        from smartarchive.config import find_tesseract
        from smartarchive.processing.ocr import TesseractEngine
        self.engine = TesseractEngine(find_tesseract(), languages, 120, tessdata)
        self.version = f'{self.engine.version()} {self.engine.languages}'

    def lines(self, image):
        return [line.text for line in self.engine.recognize(image)]


class Paddle:
    name = 'paddle'

    def __init__(self):
        import paddleocr
        from paddleocr import PaddleOCR
        self.version = getattr(paddleocr, '__version__', '?')
        self.ocr = PaddleOCR(lang='ar', use_doc_orientation_classify=False, use_doc_unwarping=False,
                             use_textline_orientation=False)

    def lines(self, image):
        import numpy as np
        result = self.ocr.predict(np.asarray(image.convert('RGB')))
        items = []
        for page in result:  # OCRResult is dict-like: rec_texts and rec_boxes (x0, y0, x1, y1)
            for text, box in zip(page['rec_texts'], page['rec_boxes']):
                items.append((tuple(float(v) for v in box), text))
        return reading_order(items)


class Easy:
    name = 'easyocr'

    def __init__(self):
        import easyocr
        self.version = easyocr.__version__
        self.reader = easyocr.Reader(['ar', 'en'], gpu=_cuda())

    def lines(self, image):
        import numpy as np
        items = []
        for points, text, _ in self.reader.readtext(np.asarray(image.convert('RGB'))):
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            items.append(((min(xs), min(ys), max(xs), max(ys)), text))
        return reading_order(items)


def _cuda() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def digits(text: str) -> str:
    return ' '.join(re.sub(r'\D', '', text.translate(DIGITS)))


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--per-level', type=int, default=8)
    parser.add_argument('--engines', default='paddle,easyocr,tesseract')
    parser.add_argument('--languages', default='script/Arabic+ara')
    parser.add_argument('--tessdata', type=Path, default=ROOT / 'models' / 'tessdata')
    parser.add_argument('--dpi', type=int, default=200)
    args = parser.parse_args(argv)
    if 'corpus_v2' in str(args.corpus):
        parser.error('the probe is for the development set; corpus_v2 is the held-out test set')
    from smartarchive.operations.evaluation import _measure
    from smartarchive.processing.preprocess import prepare
    from smartarchive.processing.quality import assess
    from smartarchive.processing.render import page_images
    manifest = json.loads((args.corpus / 'manifest.json').read_text(encoding='utf-8'))['documents']
    taken, sample = defaultdict(int), []
    for entry in manifest:
        if not entry['relations'] and taken[entry['quality']] < args.per_level:
            taken[entry['quality']] += 1
            sample.append(entry)
    pages = []
    for entry in sample:
        truth = json.loads((args.corpus / 'ground_truth' / f"{entry['doc_id']}.json").read_text(encoding='utf-8'))
        mime = 'application/pdf' if entry['file'].endswith('.pdf') else 'image/png'
        for page_no, image, dpi, source in page_images(args.corpus / entry['file'], mime, args.dpi):
            quality = assess(image, max(dpi, 300) if source == 'rendered' else dpi)
            prepared = prepare(image, quality, None).image
            pages.append((entry, page_no, prepared, truth['pages'][page_no - 1]['text']))
    print(f'{len(pages)} pages from {len(sample)} documents', flush=True)

    factories = {'tesseract': lambda: Tesseract(args.languages, args.tessdata), 'paddle': Paddle, 'easyocr': Easy}
    report = {'corpus': str(args.corpus), 'pages': len(pages), 'dpi': args.dpi,
              'started_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'engines': {}}
    for name in args.engines.split(','):
        try:
            engine = factories[name]()
        except Exception as exc:  # an engine that cannot load is reported, not hidden
            report['engines'][name] = {'error': f'{type(exc).__name__}: {exc}'[:400]}
            print(f'{name}: cannot load: {exc}', flush=True)
            continue
        rows, started = [], time.time()
        for entry, page_no, image, truth in pages:
            lines = engine.lines(image)
            forward = '\n'.join(lines)
            backward = '\n'.join(line[::-1] for line in lines)
            measured = {'forward': _measure(truth, forward), 'reversed': _measure(truth, backward)}
            rows.append({'doc_id': entry['doc_id'], 'quality': entry['quality'], 'layout': entry['layout'],
                         'forward': measured['forward'], 'reversed': measured['reversed'],
                         'digits_f': _measure(digits(truth), digits(forward))['cer'],
                         'digits_r': _measure(digits(truth), digits(backward))['cer'], 'sample': forward[:300]})
        seconds = time.time() - started
        orientation = min(('forward', 'reversed'),
                          key=lambda o: sum(r[o]['cer']['distance'] for r in rows))
        dig = 'digits_f' if orientation == 'forward' else 'digits_r'

        def block(items):
            def rate(key):
                units = sum(r[orientation][key]['reference_units'] for r in items)
                return round(sum(r[orientation][key]['distance'] for r in items) / units, 4) if units else None
            dunits = sum(r[dig]['reference_units'] for r in items)
            return {'pages': len(items), 'cer': rate('cer'), 'wer': rate('wer'),
                    'digit_cer': round(sum(r[dig]['distance'] for r in items) / dunits, 4) if dunits else None}

        summary = {'version': engine.version, 'orientation': orientation, 'seconds_per_page': round(seconds / len(rows), 2),
                   'all': block(rows)}
        for key in ('quality', 'layout'):
            groups = defaultdict(list)
            for row in rows:
                groups[row[key]].append(row)
            summary[f'by_{key}'] = {group: block(items) for group, items in sorted(groups.items())}
        summary['samples'] = [{'doc_id': r['doc_id'], 'quality': r['quality'], 'text': r['sample']} for r in rows[:5]]
        report['engines'][name] = summary
        print(f"{name}: CER {summary['all']['cer']}, digits {summary['all']['digit_cer']}, "
              f"{summary['seconds_per_page']} s/page ({orientation})", flush=True)

    out = ROOT / 'results' / 'ocr_probe'
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    (out / f'probe_{stamp}.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    lines = [f"# OCR engine probe ({report['pages']} pages, development set, {args.dpi} dpi)", '',
             '| Engine | CER | WER | Digit CER | s/page | Born-digital | Clean | Mild | Medium | Severe |',
             '|---|---|---|---|---|---|---|---|---|---|']
    pct = lambda v: '—' if v is None else f'{v * 100:.1f}%'
    for name, s in report['engines'].items():
        if 'error' in s:
            lines.append(f'| {name} | error: {s["error"][:80]} |||||||||')
            continue
        q = s['by_quality']
        lines.append(f"| {name} {s['version']} | {pct(s['all']['cer'])} | {pct(s['all']['wer'])} | "
                     f"{pct(s['all']['digit_cer'])} | {s['seconds_per_page']} | "
                     + ' | '.join(pct(q.get(level, {}).get('cer')) for level in
                                  ('born_digital', 'clean', 'mild', 'medium', 'severe')) + ' |')
    (out / f'probe_{stamp}.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
