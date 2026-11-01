r"""Generate reproducible degraded copies of real pages for OCR simulation experiments.

Example:
  .\.venv\Scripts\python.exe tools/degrade_pages.py data/input/sample.png --seed 7
Outputs go to a new results/degradation/<run>/ directory with a manifest; nothing is overwritten.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from smartarchive.processing.degrade import LEVELS, degrade  # noqa: E402
from smartarchive.processing.render import page_images  # noqa: E402
from smartarchive.persistence.storage import EXTENSIONS  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('sources', nargs='+', type=Path)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--levels', default=','.join(LEVELS))
    parser.add_argument('--output-root', type=Path, default=ROOT / 'results' / 'degradation')
    args = parser.parse_args(argv)
    levels = [level for level in args.levels.split(',') if level]
    unknown = [level for level in levels if level not in LEVELS]
    if unknown:
        parser.error(f'unknown levels: {unknown}')
    run = args.output_root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex)
    run.mkdir(parents=True, exist_ok=False)
    entries = []
    for source in args.sources:
        mime = EXTENSIONS.get(source.suffix.lower())
        if not mime or not source.is_file():
            parser.error(f'unsupported or missing source: {source}')
        digest = sha256(source)
        for page_no, image, dpi, dpi_source in page_images(source, mime, 300):
            for level in levels:
                result = degrade(image, level, args.seed)
                target = run / f'{source.stem}__p{page_no:03d}__{level}.png'
                result.image.save(target, format='PNG')
                entries.append({'source': str(source), 'source_sha256': digest, 'page': page_no,
                                'source_dpi': round(dpi, 1), 'source_dpi_source': dpi_source, 'level': level,
                                'params': result.params, 'output': target.name, 'output_sha256': sha256(target)})
    (run / 'manifest.json').write_text(json.dumps({'created_at': datetime.now(timezone.utc).isoformat(),
                                                   'seed': args.seed, 'levels': {k: LEVELS[k] for k in levels},
                                                   'items': entries}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote {len(entries)} degraded pages to {run}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
