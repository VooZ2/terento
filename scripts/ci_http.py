#!/usr/bin/env python3
"""Bounded CI HTTP transport. Assertions belong to callers, never retries.

Exit 75 means transient transport failures exhausted all three attempts.
Only replay safe requests or idempotent observation payloads with a fixed ID.
"""
import pathlib
import subprocess
import sys
import tempfile
import time

TRANSIENT_CURL = {5, 6, 7, 18, 28, 52, 55, 56}
TRANSIENT_HTTP = {408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526}


def request(label, args, run=subprocess.run, sleep=time.sleep):
    args = list(args)
    output, write_status, fail = None, False, False
    forwarded = []
    while args:
        arg = args.pop(0)
        if arg in ('--fail', '-f'):
            fail = True
        elif arg in ('--output', '-o'):
            output = args.pop(0)
        elif arg in ('--write-out', '-w'):
            if args.pop(0) != '%{http_code}':
                raise ValueError('only HTTP status write-out is supported')
            write_status = True
        elif arg.startswith('--retry'):
            raise ValueError('nested retries are not supported')
        else:
            forwarded.append(arg)
    with tempfile.TemporaryDirectory(prefix='terento-ci-http-') as directory:
        body = pathlib.Path(directory) / 'body'
        for attempt in range(1, 4):
            body.write_bytes(b'')
            result = run(['curl', '--compressed', '--proto', '=https',
                          '--proto-redir', '=https', *forwarded,
                          '--output', str(body), '--write-out', '%{http_code}'],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            status = result.stdout.decode().strip()
            transient = (result.returncode in TRANSIENT_CURL or
                         (result.returncode == 0 and status.isdigit() and
                          int(status) in TRANSIENT_HTTP))
            if transient:
                print(f'{label}: transient HTTP {status or "unknown"}, curl {result.returncode}; attempt {attempt}/3', file=sys.stderr)
                if attempt < 3:
                    sleep(attempt * 2)
                    continue
                return 75, b''
            if result.returncode or not status.isdigit() or (fail and int(status) >= 400):
                print(f'{label}: HTTP {status or "unknown"}, curl {result.returncode}', file=sys.stderr)
                return 1, b''
            data = body.read_bytes()
            if output:
                pathlib.Path(output).write_bytes(data)
            return 0, status.encode() if write_status else (b'' if output else data)
    raise AssertionError('unreachable')


def main():
    args = sys.argv[1:]
    observation = args and args[0] == '--observation'
    if observation:
        args.pop(0)
    code, data = request(args[0], args[1:])
    if observation and code == 75:
        message = f'{args[0]}: report delivery unavailable after retries; quality result is unchanged.'
        print(f'::warning::{message}', file=sys.stderr)
        import os
        summary = os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary, 'a') as handle:
                handle.write('\n' + message + '\n')
        return 0
    sys.stdout.buffer.write(data)
    return code


if __name__ == '__main__':
    sys.exit(main())
