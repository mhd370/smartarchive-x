"""Exclusive local run directories and immutable per-run file writes."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import unicodedata
import uuid

from .validation import digest


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value) -> None:
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def create_run(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    # UUID plus exclusive mkdir prevents overwrite even if a name collides.
    run = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex)
    run.mkdir(exist_ok=False)
    return run


def environment() -> dict:
    modules = sorted(Path(__file__).parent.glob('*.py'))
    return {
        'python': sys.version, 'executable': sys.executable,
        'platform': platform.platform(), 'unicode_database': unicodedata.unidata_version,
        'argv': sys.argv, 'working_directory': str(Path.cwd()),
        'benchmark_source_sha256': {p.name: digest(p.read_bytes()) for p in modules},
        'dependencies': 'Python standard library only; no OCR engine invoked',
    }
