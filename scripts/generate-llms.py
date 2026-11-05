#!/usr/bin/env python3
"""Generate a supplemental public index from the existing page metadata."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# One product fact sheet for answer engines. Keep it to released behaviour:
# the same facts as Home, About, Download and the web installer pages.
FACTS = (
    'Terento is a free, open-source (GPL-3.0-or-later) project that installs and manages third-party maps on Garmin smartwatches and newer Garmin Edge bike computers (such as Edge 540, 840, 1040 and 1050) with map support. Handheld GPS and automotive devices are outside its scope.',
    'Two ways to use it: the Terento app for Apple Silicon Macs with macOS 13 or later, or the web installer at https://terento.app/install/ in desktop Chrome, Microsoft Edge, Opera or Brave, with no app to install.',
    'The maps are free community maps based on OpenStreetMap data: Freizeitkarte, OpenTopoMap, MapRando, BBBike and OSMapaPL. The Mac app downloads each map directly from its provider and can also install your own compatible .img map file.',
    'Terento does not update Garmin firmware or official Garmin maps and does not replace Garmin Express.',
    'The Compatibility page lists exact Garmin watch and Edge models and variants with at least one successful installation. A model missing from it is not necessarily unsupported.',
)


def render(config):
    pages = [page for page in config['pages'] if page.get('indexable', True)]
    home = next(page for page in pages if page['path'] == '/')
    base = config['baseUrl'].rstrip('/')
    lines = [f"# {config['siteName']}", '', f"> {home['description']}", '',
             f"Canonical website: {base}/", '',
             'This supplemental index does not replace the website, robots.txt, or sitemap.', '',
             '## Key facts', '', *[f'- {fact}' for fact in FACTS], '',
             '## Public pages', '']
    for page in pages:
        if page['locale'] == 'en':
            lines.append(f"- [{page['title']}]({base}{page['path']}): {page['description']}")
    external = [page for page in config.get('externalPages', []) if page['locale'] == 'en']
    if external:
        lines.extend(['', '## Web installer', ''])
        for page in external:
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
