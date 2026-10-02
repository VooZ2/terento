#!/usr/bin/env python3
"""Generate a supplemental public index from the existing page metadata."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render(config):
    pages = [page for page in config['pages'] if page.get('indexable', True)]
    home = next(page for page in pages if page['path'] == '/')
    base = config['baseUrl'].rstrip('/')
    lines = [f"# {config['siteName']}", '', f"> {home['description']}", '',
             f"Canonical website: {base}/", '',
             'This supplemental index does not replace the website, robots.txt, or sitemap.', '',
             '## Public pages', '']
    for page in pages:
        if page['locale'] == 'en':
            lines.append(f"- [{page['title']}]({base}{page['path']}): {page['description']}")
    lines.extend(['', '## Other languages', ''])
    for page in pages:
        if page['path'] == f"/{page['locale']}/":
            lines.append(f"- [{page['locale']}]({base}{page['path']})")
    lines.extend(['', '## Source', '',
                  '- [Official repository](https://github.com/VooZ2/terento)', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    output = render(json.loads((ROOT / 'site/metadata.json').read_text()))
    target = ROOT / 'site/llms.txt'
    if args.write:
        target.write_text(output)
    elif not target.exists() or target.read_text() != output:
        parser.exit(1, 'site/llms.txt is stale; run scripts/generate-llms.py --write\n')
    print('Supplemental public index passed.')


if __name__ == '__main__':
    main()
