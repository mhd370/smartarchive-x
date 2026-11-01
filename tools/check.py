r"""One command for the local quality gate (stands in for CI while the repository is local).

  .\.venv\Scripts\python.exe tools/check.py            # Python tests + preservation + TypeScript
  .\.venv\Scripts\python.exe tools/check.py --full     # + production build + browser tests

Writes a JSON report to results/checks/ and exits non-zero if any step fails.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def steps(full: bool) -> list[tuple[str, list[str]]]:
    plan = [('python-tests', [PY, '-m', 'unittest', 'discover', '-s', 'tests']),
            ('preservation-108', [PY, 'tools/verify_preservation.py'])]
    for task in ('003', '004', '005', '006', '007'):
        manifest = ROOT / 'docs' / f'task_{task}_preservation.json'
        if manifest.is_file():
            plan.append((f'snapshot-{task}', [PY, 'tools/verify_snapshot.py', '--manifest', f'docs/task_{task}_preservation.json']))
    plan.append(('typescript', [PY, 'tools/frontend.py', 'run', 'typecheck']))
    if full:
        plan += [('frontend-build', [PY, 'tools/frontend.py', 'run', 'build']),
                 ('browser-tests', [PY, 'tools/frontend.py', 'run', 'test:e2e'])]
    return plan


def main(argv=None) -> int:
    # Windows consoles and redirected output default to cp1252; tool output contains Unicode.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--full', action='store_true', help='also run the production build and browser tests')
    args = parser.parse_args(argv)
    results = []
    for name, command in steps(args.full):
        print(f'\n==== {name}: {" ".join(command[1:])}', flush=True)
        started = time.time()
        completed = subprocess.run(command, cwd=ROOT, text=True, encoding='utf-8', errors='replace',
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(completed.stdout[-6000:], flush=True)
        results.append({'step': name, 'command': command[1:], 'exit_code': completed.returncode,
                        'seconds': round(time.time() - started, 1), 'tail': completed.stdout[-3000:]})
    report = ROOT / 'results' / 'checks'
    report.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = report / f'check_{stamp}.json'
    path.write_text(json.dumps({'created_at': stamp, 'full': args.full, 'steps': results}, ensure_ascii=False, indent=2),
                    encoding='utf-8')
    print('\n==== SUMMARY')
    for item in results:
        print(f"{'PASS' if item['exit_code'] == 0 else 'FAIL'}  {item['step']}  ({item['seconds']}s)")
    failed = [item['step'] for item in results if item['exit_code']]
    print(('ALL CHECKS PASSED' if not failed else f'FAILED: {", ".join(failed)}') + f'\nReport: {path.relative_to(ROOT)}')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
