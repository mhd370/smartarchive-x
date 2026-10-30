"""Run npm using installed/portable Node, without shell quoting.

Examples: python tools/frontend.py install; python tools/frontend.py run dev
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import getproxies

ROOT = Path(__file__).resolve().parents[1]


def main():
    node = shutil.which('node')
    if not node:
        candidates = sorted((ROOT / '.tools').glob('node-*-win-x64/node.exe'))
        node = str(candidates[-1]) if candidates else None
    if not node:
        raise SystemExit('Install Node.js LTS (20.9+), reopen PowerShell, then rerun this command.')
    node_directory = Path(node).resolve().parent
    npm = node_directory / 'node_modules/npm/bin/npm-cli.js'
    if not npm.is_file():
        raise SystemExit('npm was not found next to Node. Use npm directly or install the Node LTS distribution.')
    env = os.environ.copy()
    env['PATH'] = str(node_directory) + os.pathsep + env.get('PATH', '')
    # Python reads Windows proxy settings; npm does not reliably discover them.
    # Values stay in child environment and are never logged or saved to .npmrc.
    proxies = getproxies()
    for protocol in ('https', 'http'):
        if proxies.get(protocol):
            env.setdefault(f'npm_config_{protocol}_proxy' if protocol == 'https' else 'npm_config_proxy', proxies[protocol])
    env.setdefault('NEXT_TELEMETRY_DISABLED', '1')
    if os.name == 'nt':
        # Keep Node on IPv4 on Windows networks with an unreachable IPv6 route.
        # This changes only the child process; certificate validation stays on.
        env.setdefault('NODE_OPTIONS', '--dns-result-order=ipv4first --no-network-family-autoselection')
    args = sys.argv[1:] or ['run', 'dev']
    try:
        return subprocess.call([node, str(npm), *args], cwd=ROOT / 'frontend', env=env)
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
