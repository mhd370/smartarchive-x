r"""Several OCR paths per page and the automatic choice between them (processing/paths.py, ADR 0016).

  .\.venv\Scripts\python.exe tools/ocr_paths_experiment.py data\synthetic\corpus_v1 --per-level 14 ^
      --languages script/Arabic+ara --tessdata models\tessdata
  .\.venv\Scripts\python.exe tools/ocr_paths_experiment.py data\synthetic\corpus_v2 --per-level 20 ^
      --languages script/Arabic+ara --tessdata models\tessdata --choose-from results\ocr_paths\corpus_v1.json

For a sample of documents per scan quality (documents without relations, in manifest order), every page goes
through the archive's own quality assessment, preprocessing and layout analysis, and is then read on each OCR
path (standard, binarized, upscaled, model-ara). Every path's text is measured against the ground truth (CER,
normalized-v1), and its confidence and time are kept, so every choice rule can be scored without new OCR:
- each path alone, and the oracle (the best path per page, an upper bound no rule can use);
- every set of paths that includes `standard`, with each rule (confidence, confident-chars) and each gate.
On the development set the configuration with the lowest CER is chosen; among configurations within 0.2 points
of it, the one with the least OCR time. On the test set (--choose-from the development json) the chosen
configuration is measured once. Results: results/ocr_paths/<corpus>.json and .md. Synthetic data.
"""
import argparse
from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
GATES = (1.0, 0.9, 0.8, 0.7, 0.6)
TOLERANCE = 0.002
LEVELS = ('born_digital', 'clean', 'mild', 'medium', 'severe')


def sample(corpus: Path, per_level: int) -> list[dict]:
    manifest = json.loads((corpus / 'manifest.json').read_text(encoding='utf-8'))['documents']
    taken, out = defaultdict(int), []
    for entry in manifest:
        if not entry.get('relations') and taken[entry['quality']] < per_level:
            taken[entry['quality']] += 1
            out.append(entry)
    return out


def read_pages(corpus: Path, entries: list[dict], args, log=print) -> list[dict]:
    """OCR every page on every path; one row per page with each path's text score, confidence and time."""
    from smartarchive.config import Settings
    from smartarchive.operations.evaluation import _measure
    from smartarchive.processing import paths
    from smartarchive.processing.layout import read_page
    from smartarchive.processing.ocr import TesseractEngine, mean_confidence
    from smartarchive.processing.pipeline import FULL_RESOLUTION_DPI
    from smartarchive.processing.preprocess import prepare
    from smartarchive.processing.quality import assess
    from smartarchive.processing.render import page_images
    settings = Settings.from_env()
    command = settings.tesseract
    if not command:
        raise SystemExit('Tesseract not found')
    tessdata = args.tessdata.resolve() if args.tessdata else None
    engines = {None: TesseractEngine(command, args.languages, 120, tessdata)}

    def engine_for(languages):
        if languages not in engines:
            engines[languages] = TesseractEngine(command, languages, 120, tessdata)
        return engines[languages]
    rows, started = [], time.time()
    for number, entry in enumerate(entries, 1):
        truth = json.loads((corpus / 'ground_truth' / f"{entry['doc_id']}.json").read_text(encoding='utf-8'))
        mime = 'application/pdf' if entry['file'].lower().endswith('.pdf') else 'image/png'
        for page_no, image, dpi, source in page_images(corpus / entry['file'], mime, args.dpi):
            quality = assess(image, max(dpi, FULL_RESOLUTION_DPI) if source == 'rendered' else dpi,
                             settings.quality_weights)
            if quality.blank:
                continue
            prepared = prepare(image, quality, command).image
            reference = truth['pages'][page_no - 1]['text']
            row = {'doc_id': entry['doc_id'], 'page_no': page_no, 'quality': entry['quality'],
                   'layout': entry['layout'], 'paths': {}}
            for name in paths.PATHS:
                path = paths.variant(name, prepared)
                tick = time.time()
                lines, _ = read_page(engine_for(path.languages), path.image)
                lines = paths.rescale(lines, path.scale)
                seconds = time.time() - tick
                measured = _measure(reference, '\n'.join(line.text for line in lines))['cer']
                words = [w for line in lines for w in line.words]
                row['paths'][name] = {'distance': measured['distance'], 'units': measured['reference_units'],
                                      'confidence': mean_confidence(words),
                                      'confident-chars': round(paths.score(lines, 'confident-chars'), 3),
                                      'seconds': round(seconds, 3)}
            rows.append(row)
        if number % 5 == 0:
            log(f'  {number}/{len(entries)} documents, {len(rows)} pages, {time.time() - started:.0f}s', flush=True)
    return rows


def evaluate(rows: list[dict], chosen_paths: tuple[str, ...], rule: str | None, gate: float) -> dict:
    """CER, mean OCR seconds per page and how often each path was chosen, for one configuration.
    rule None with one path: that path alone; rule 'oracle': the lowest-distance path per page."""
    from smartarchive.processing.paths import PATHS
    distance = units = seconds = 0
    picks, by_level = defaultdict(int), defaultdict(lambda: [0, 0])
    for row in rows:
        p = row['paths']
        first = chosen_paths[0]
        tried = [first]
        confidence = p[first]['confidence']
        if len(chosen_paths) > 1 and (rule == 'oracle' or confidence is None or confidence < gate):
            tried = list(chosen_paths)
        if rule == 'oracle':
            pick = min(tried, key=lambda n: (p[n]['distance'], PATHS.index(n)))
        elif len(tried) == 1:
            pick = first
        else:
            key = (lambda n: -1.0 if p[n]['confidence'] is None else p[n]['confidence']) if rule == 'confidence' \
                else (lambda n: p[n]['confident-chars'])
            pick = max(tried, key=lambda n: (key(n), -PATHS.index(n)))
        picks[pick] += 1
        distance += p[pick]['distance']
        units += p[pick]['units']
        seconds += sum(p[n]['seconds'] for n in tried)
        by_level[row['quality']][0] += p[pick]['distance']
        by_level[row['quality']][1] += p[pick]['units']
    return {'paths': list(chosen_paths), 'rule': rule, 'gate': gate, 'pages': len(rows),
            'cer': round(distance / units, 4) if units else None,
            'seconds_per_page': round(seconds / max(1, len(rows)), 2), 'chosen': dict(picks),
            'by_quality': {level: round(d / u, 4) for level, (d, u) in sorted(by_level.items()) if u}}


def configurations() -> list[tuple[tuple[str, ...], str, float]]:
    from smartarchive.processing.paths import PATHS, RULES
    others = [name for name in PATHS if name != 'standard']
    out = []
    for size in range(1, len(others) + 1):
        for extra in combinations(others, size):
            for rule in RULES:
                for gate in GATES:
                    out.append((('standard',) + extra, rule, gate))
    return out


def markdown(report: dict) -> str:
    pct = lambda v: '—' if v is None else f'{v * 100:.1f}%'
    lines = [f"# OCR paths ({report['corpus']}, {report['pages']} pages from {report['documents']} documents)", '',
             'Synthetic data. CER (normalized-v1, micro-averaged); seconds = OCR time per page for the paths read.', '',
             '| Configuration | CER | s/page | ' + ' | '.join(LEVELS) + ' |', '|---|---|---|' + '---|' * len(LEVELS)]
    for name, block in report['results'].items():
        lines.append(f"| {name} | {pct(block['cer'])} | {block['seconds_per_page']} | "
                     + ' | '.join(pct(block['by_quality'].get(level)) for level in LEVELS) + ' |')
    if report.get('chosen'):
        c = report['chosen']
        lines += ['', f"Chosen on the development set: paths {'+'.join(c['paths'])}, rule {c['rule']}, gate {c['gate']}."]
    return '\n'.join(lines) + '\n'


def label(paths_, rule, gate) -> str:
    return f"{'+'.join(paths_)} · {rule} · gate {gate:g}"


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--per-level', type=int, default=14)
    parser.add_argument('--languages', default='script/Arabic+ara')
    parser.add_argument('--tessdata', type=Path, default=ROOT / 'models' / 'tessdata')
    parser.add_argument('--dpi', type=int, default=200)
    parser.add_argument('--out', type=Path, default=ROOT / 'results' / 'ocr_paths')
    parser.add_argument('--choose-from', type=Path, help="the development set's json: measure its chosen configuration")
    parser.add_argument('--reuse', action='store_true', help='score the pages already read (rows in the json)')
    args = parser.parse_args(argv)
    from smartarchive.processing.paths import PATHS
    corpus = args.corpus.resolve()
    if 'corpus_v2' in corpus.name and not args.choose_from:
        parser.error('corpus_v2 is the held-out test set: give --choose-from with the development results')
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / f'{corpus.name}.json'
    entries = sample(corpus, args.per_level)
    if args.reuse and target.is_file():
        rows = json.loads(target.read_text(encoding='utf-8'))['rows']
    else:
        print(f'{len(entries)} documents sampled from {corpus.name}', flush=True)
        rows = read_pages(corpus, entries, args)
    results = {f'{name} alone': evaluate(rows, (name,), None, 1.0) for name in PATHS}
    results['oracle (best path per page)'] = evaluate(rows, PATHS, 'oracle', 1.0)
    if args.choose_from:
        chosen = json.loads(args.choose_from.read_text(encoding='utf-8'))['chosen']
        block = evaluate(rows, tuple(chosen['paths']), chosen['rule'], chosen['gate'])
        results[f"chosen: {label(chosen['paths'], chosen['rule'], chosen['gate'])}"] = block
    else:
        scored = [evaluate(rows, *config) for config in configurations()]
        best = min(s['cer'] for s in scored)
        chosen = min((s for s in scored if s['cer'] <= best + TOLERANCE), key=lambda s: (s['seconds_per_page'], s['cer']))
        chosen = {k: chosen[k] for k in ('paths', 'rule', 'gate')}
        for s in sorted(scored, key=lambda s: s['cer'])[:12]:
            results[label(s['paths'], s['rule'], s['gate'])] = s
        block = evaluate(rows, tuple(chosen['paths']), chosen['rule'], chosen['gate'])
        results[f"chosen: {label(chosen['paths'], chosen['rule'], chosen['gate'])}"] = block
    report = {'corpus': corpus.name, 'synthetic': True, 'documents': len(entries), 'pages': len(rows),
              'languages': args.languages, 'dpi': args.dpi, 'chosen': chosen, 'results': results, 'rows': rows}
    target.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    (args.out / f'{corpus.name}.md').write_text(markdown(report), encoding='utf-8')
    print(markdown(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
