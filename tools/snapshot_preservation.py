r"""Record SHA-256 hashes of files a task did not change, for later tamper/regression checks.

  .\.venv\Scripts\python.exe tools/snapshot_preservation.py --base v0.5.0 --task 006

Covers every file tracked at --base that the working tree did not change since then, plus every
entry of the previous task's manifest (historical inputs and results). Read-only on all of them.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> list[str]:
    output = subprocess.run(['git', '-c', 'core.quotepath=off', *args], cwd=ROOT, check=True,
                            capture_output=True, text=True, encoding='utf-8').stdout
    return [line for line in output.splitlines() if line]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', required=True)
    parser.add_argument('--task', required=True)
    args = parser.parse_args(argv)
    previous = sorted(ROOT.glob('docs/task_*_preservation.json'))
    target = ROOT / 'docs' / f'task_{args.task}_preservation.json'
    if target.exists():
        parser.error(f'{target.name} already exists; snapshots are never overwritten')
    changed = set(git('diff', '--name-only', args.base)) | set(git('ls-files', '--others', '--exclude-standard'))
    paths = set(git('ls-tree', '-r', '--name-only', args.base)) - changed
    if previous:
        paths |= {entry['path'] for entry in json.loads(previous[-1].read_text(encoding='utf-8'))['files']}
    files = []
    for name in sorted(paths):
        path = ROOT / name
        if path.is_file():
            files.append({'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size': path.stat().st_size})
    target.write_text(json.dumps({'task': args.task, 'base': args.base, 'created_at': datetime.now(timezone.utc).isoformat(),
                                  'note': 'Pre-task files left unchanged by this task.', 'files': files},
                                 ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Recorded {len(files)} unchanged files in {target.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
