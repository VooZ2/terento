#!/usr/bin/env python3
"""Read-only preflight for new public builds; never rewrites published history."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = 'VooZ2/terento'


def run(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True, timeout=60).strip()


def verify():
    if run('git', 'status', '--porcelain', '--untracked-files=normal'):
        raise ValueError('Release source must be a clean checkout (including untracked files).')
    sha = run('git', 'rev-parse', 'HEAD')
    commit = json.loads(run('gh', 'api', f'repos/{REPO}/commits/{sha}'))
    verification = commit.get('commit', {}).get('verification', {})
    if commit.get('sha') != sha or verification.get('verified') is not True or verification.get('reason') != 'valid':
        raise ValueError('GitHub must verify the exact release commit signature before packaging. '
                         'Use the verified beta merge commit, not an unsigned PR head.')
    comparison = json.loads(run('gh', 'api', f'repos/{REPO}/compare/{sha}...beta'))
    if comparison.get('status') not in ('ahead', 'identical'):
        raise ValueError('Release source must already be merged into beta.')
    return sha


if __name__ == '__main__':
    try:
        print('Verified GitHub release source: ' + verify())
    except (ValueError, KeyError, subprocess.SubprocessError, OSError) as error:
        print(f'Release source preflight failed: {error}', file=sys.stderr)
        sys.exit(1)
