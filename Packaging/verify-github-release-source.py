#!/usr/bin/env python3
"""Read-only preflight for new public builds; never rewrites published history."""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = 'VooZ2/terento'


def run(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True, timeout=60).strip()


def source_branch(release_label):
    """Stable releases come from main; beta and RC prereleases from beta."""
    if re.fullmatch(r'\d+\.\d+\.\d+', release_label):
        return 'main'
    if re.fullmatch(r'\d+\.\d+\.\d+-(beta|rc)\.[1-9]\d*', release_label):
        return 'beta'
    raise ValueError(f'Release label {release_label!r} is neither stable nor a beta/RC prerelease.')


def verify(release_label):
    branch = source_branch(release_label)
    if run('git', 'status', '--porcelain', '--untracked-files=normal'):
        raise ValueError('Release source must be a clean checkout (including untracked files).')
    sha = run('git', 'rev-parse', 'HEAD')
    commit = json.loads(run('gh', 'api', f'repos/{REPO}/commits/{sha}'))
    verification = commit.get('commit', {}).get('verification', {})
    if commit.get('sha') != sha or verification.get('verified') is not True or verification.get('reason') != 'valid':
        raise ValueError('GitHub must verify the exact release commit signature before packaging. '
                         f'Use the verified {branch} merge commit, not an unsigned PR head.')
    comparison = json.loads(run('gh', 'api', f'repos/{REPO}/compare/{sha}...{branch}'))
    if comparison.get('status') not in ('ahead', 'identical'):
        raise ValueError(f'Release source must already be merged into {branch}.')
    return sha


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('usage: verify-github-release-source.py RELEASE_LABEL')
        print('Verified GitHub release source: ' + verify(sys.argv[1]))
    except (ValueError, KeyError, subprocess.SubprocessError, OSError) as error:
        print(f'Release source preflight failed: {error}', file=sys.stderr)
        sys.exit(1)
