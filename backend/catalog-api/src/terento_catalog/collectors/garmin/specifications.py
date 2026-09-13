"""Exact-product specification enrichment; never changes canonical IDs."""
import json
import re
from html.parser import HTMLParser


class SpecificationTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = {}
        self.label = ''
        self.value = ''
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.label, self.value = '', ''
        if tag in ('th', 'td'):
            self.cell = tag
            if tag == 'td':
                cls = dict(attrs).get('class', '').split()
                if 'yes' in cls:
                    self.value = 'yes'
                elif 'no' in cls:
                    self.value = 'no'

    def handle_data(self, data):
        if self.cell == 'th':
            self.label += data
        elif self.cell == 'td':
            self.value += data

    def handle_endtag(self, tag):
        if tag in ('th', 'td'):
            self.cell = None
        if tag == 'tr' and self.label.strip():
            key, value = self.label.strip().lower(), self.value.strip()
            self.rows[key] = value if key not in self.rows or self.rows[key] == value else ''


def parse_specifications(html: str, product_id: str) -> dict:
    marker = 'var GarminAppBootstrap = '
    if marker not in html:
        return {}
    bootstrap, _ = json.JSONDecoder().raw_decode(html.split(marker, 1)[1])
    variants = []
    skus = []
    for sku in bootstrap.get('skus', {}).values():
        if str(sku.get('productId')) != str(product_id):
            continue
        code = sku.get('partNumber', '')
        if re.fullmatch(r'010-[A-Za-z0-9-]+', code):
            skus.append(code)
        table = SpecificationTable()
        table.feed(sku.get('tabs', {}).get('specsTab', {}).get('content', ''))
        display = table.rows.get('display type', '').lower()
        technologies = {name for token, name in (('microled', 'MicroLED'), ('amoled', 'AMOLED'), ('mip', 'MIP'))
                        if re.search(r'\b' + token + r'\b', display)}
        if 'memory-in-pixel' in display or 'memory in pixel' in display:
            technologies.add('MIP')
        screen = next(iter(technologies)) if len(technologies) == 1 else None
        solar_value = table.rows.get('solar charging')
        inreach_value = table.rows.get('inreach technology')
        satellite = table.rows.get('satellite communication', '').lower()
        if satellite.startswith('yes') and 'inreach' in satellite:
            inreach_value = 'yes'
        variants.append({'screen_technology': screen,
                         'solar': {'yes': True, 'no': False}.get(solar_value),
                         'inreach': {'yes': True, 'no': False}.get(inreach_value)})
    result = {'retail_skus': sorted(set(skus))}
    for key in ('screen_technology', 'solar', 'inreach'):
        values = {v[key] for v in variants}
        result[key] = next(iter(values)) if len(values) == 1 else None
    return result
