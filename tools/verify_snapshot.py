"""Read-only verification of an explicitly selected preservation manifest."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('docs/task_003_preservation.json'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / args.manifest).read_text(encoding='utf-8'))
    failed = []
    for entry in manifest['files']:
        path = root / entry['path']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            failed.append(entry['path'])
    for path in failed:
        print(f'CHANGED OR MISSING: {path}')
    print(f"Checked {len(manifest['files'])} pre-task files; failures={len(failed)}")
    return int(bool(failed))


if __name__ == '__main__':
    raise SystemExit(main())
