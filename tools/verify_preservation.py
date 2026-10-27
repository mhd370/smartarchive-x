"""Verify pre-audit experimental bytes without importing or rerunning experiments."""
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'docs/preservation_manifest.json').read_text(encoding='utf-8'))
    failures = []
    for entry in manifest['files']:
        path = root / entry['path']
        if not path.is_file():
            failures.append(f"MISSING: {entry['path']}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            failures.append(f"CHANGED: {entry['path']}")
    for failure in failures:
        print(failure)
    print(f"Verified {len(manifest['files'])} historical files; failures={len(failures)}")
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
