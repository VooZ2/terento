#!/usr/bin/env python3
"""Render the deliberately small public legal Markdown format into six locales.

Supported: H1, H2, paragraphs, unordered lists, inline bold/code/links.
No third-party Markdown runtime or raw HTML is required.
"""
from __future__ import annotations
import argparse
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ('en', 'de', 'fr', 'pl', 'cs', 'it')
CONTENTS = dict(zip(LOCALES, ('On this page', 'Auf dieser Seite', 'Sur cette page', 'Na tej stronie', 'Na této stránce', 'In questa pagina')))


def inline(text):
    text = html.escape(text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    def link(match):
        label, url = match.groups()
        if not url.startswith(('https://', '/', '#', 'mailto:')):
            raise ValueError(f'Unsupported legal link: {url}')
        return f'<a href="{url}">{label}</a>'
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, text)


def render(page, locale):
    source = (ROOT / f'legal/web/{page.upper()}-PAGE-{locale.upper()}.md').read_text()
    chunks = re.split(r'\n\s*\n', source.strip())
    if not chunks[0].startswith('# '):
        raise ValueError('Legal source must start with a title')
    intro, sections, current = [], [], None
    for chunk in chunks[1:]:
        if chunk.startswith('## '):
            lines = chunk.splitlines()
            if len(lines) != 1:
                raise ValueError('Separate headings and paragraphs with a blank line')
            current = [chunk[3:], []]
            sections.append(current)
            continue
        if chunk.startswith('- '):
            body = '<ul>' + ''.join(f'<li>{inline(line[2:])}</li>' for line in chunk.splitlines()) + '</ul>'
        else:
            body = '<p>' + inline(' '.join(chunk.splitlines())) + '</p>'
        (intro if current is None else current[1]).append(body)
    ids = [f'{page}-{locale}-{i+1}' for i in range(len(sections))]
    toc = '<nav class="legal-toc" aria-label="'+CONTENTS[locale]+'"><p class="eyebrow">'+CONTENTS[locale]+'</p><ul>'
    toc += ''.join(f'<li><a href="#{id_}">{inline(section[0])}</a></li>' for id_, section in zip(ids,sections))
    toc += '</ul></nav>'
    body = ''.join(f'<section class="legal-item" id="{id_}"><h2>{inline(title)}</h2>{"".join(paragraphs)}</section>' for id_,(title,paragraphs) in zip(ids,sections))
    return f'<div class="legal-version legal-version-{locale}" lang="{locale}">\n<h1>{inline(chunks[0][2:])}</h1>\n<div class="legal-summary">{"".join(intro)}</div>\n<div class="legal-grid">{toc}<div class="legal-list">{body}</div></div>\n</div>'


def generate(page):
    path = ROOT / f'site/{page}/index.html'
    source = path.read_text()
    start = source.index('<div class="legal-version')
    end = source.index('\n      </div>\n    </main>', start)
    source = source[:start] + '\n\n'.join(render(page,locale) for locale in LOCALES) + source[end:]
    # Keep shared link metadata identical to the public-shell normalization pass.
    import importlib.util
    spec = importlib.util.spec_from_file_location('public_shell', ROOT/'scripts/normalize-public-shell.py')
    shell = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shell)
    source = shell.normalize_internal_link_events(source,page)
    return shell.normalize_email_links(source,page)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--check',action='store_true'); args=parser.parse_args()
    for page in ('privacy','legal'):
        path=ROOT/f'site/{page}/index.html'; expected=generate(page)
        if args.check:
            if path.read_text()!=expected: raise SystemExit(f'{path}: regenerate with scripts/build-legal-pages.py')
        else: path.write_text(expected)
    print('Legal/Privacy source parity passed.' if args.check else 'Rendered legal and privacy pages in six locales.')

if __name__=='__main__': main()
