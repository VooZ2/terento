"""Exact-product specification enrichment; never changes canonical IDs."""
import json
import re
from html.parser import HTMLParser


class SpecificationTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = {}
        # Rows outside golf sections only: the map evidence (see GOLF_SECTION below).
        self.map_rows = {}
        self.section = ''
        self.heading = None
        self.label = ''
        self.value = ''
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'h3':
            self.heading = ''
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
        if self.heading is not None:
            self.heading += data
        elif self.cell == 'th':
            self.label += data
        elif self.cell == 'td':
            self.value += data

    def handle_endtag(self, tag):
        if tag == 'h3' and self.heading is not None:
            self.section, self.heading = ' '.join(self.heading.split()).lower(), None
        if tag in ('th', 'td'):
            self.cell = None
        if tag == 'tr' and self.label.strip():
            key, value = self.label.strip().lower(), self.value.strip()
            self.rows[key] = value if key not in self.rows or self.rows[key] == value else ''
            if GOLF_SECTION not in self.section:
                self.map_rows[key] = value if key not in self.map_rows or self.map_rows[key] == value else ''


# Maps evidence from the official specification table (owner rule 2026-10-06):
# an explicit "yes" on any map-support row means the model has maps; an
# explicit "no" counts only on a row that states additional-map support as a
# whole, because a watch without preloaded maps may still accept added maps.
# Anything else is unknown (NULL), never inferred from the model name.
# Live Garmin product pages (checked 2026-10-06) mark map watches with
# "Built-in mapping" and "Full vector map"; watches without maps simply omit
# those rows (Garmin publishes no explicit "no"), so they stay unknown.
# "On-screen workout muscle maps" is not map support and is never matched.
# Golf rule (owner, 2026-10-09): a row under a specification-table heading that
# contains "golf" (Garmin's "Golfing Features") describes golf-course maps, not
# outdoor/road/trail/topo map support, so it is never map evidence, yes or no.
# Garmin lists "Full vector map" only there (Approach S44/S50/S70 show nothing
# else), so a golf-only page stays Unknown; a map row in any other section
# (for example "Built-in mapping" under "What You'll Love" or "Preloaded road
# and trail maps" under "Mapping & Navigation", as on Approach S72) still counts.
GOLF_SECTION = 'golf'
MAP_POSITIVE_ROWS = ('built-in mapping', 'full vector map', 'ability to add maps', 'preloaded maps',
                     'topoactive maps', 'maps', 'map support', 'preloaded road and trail maps')
MAP_NEGATIVE_ROWS = ('built-in mapping', 'full vector map', 'ability to add maps', 'maps', 'map support')


def map_capability_from_rows(rows: dict) -> tuple[bool | None, str | None]:
    """Return (map_capable, evidence row) from one SKU's specification rows."""
    def answer(key):
        value = (rows.get(key) or '').strip().lower()
        if value.startswith('yes'):
            return True
        if value.startswith('no') and not value.startswith('none'):
            return False
        return None
    positive = [key for key in MAP_POSITIVE_ROWS if answer(key) is True]
    negative = [key for key in MAP_NEGATIVE_ROWS if answer(key) is False]
    if positive and negative:
        return None, None
    if positive:
        return True, positive[0]
    if negative:
        return False, negative[0]
    return None, None


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
        map_capable, map_row = map_capability_from_rows(table.map_rows)
        variants.append({'screen_technology': screen,
                         'solar': {'yes': True, 'no': False}.get(solar_value),
                         'inreach': {'yes': True, 'no': False}.get(inreach_value),
                         'map_capable': map_capable, 'map_evidence_row': map_row})
    result = {'retail_skus': sorted(set(skus))}
    for key in ('screen_technology', 'solar', 'inreach', 'map_capable'):
        values = {v[key] for v in variants}
        result[key] = next(iter(values)) if len(values) == 1 else None
    rows = sorted({v['map_evidence_row'] for v in variants if v['map_evidence_row']})
    result['map_evidence_row'] = rows[0] if result['map_capable'] is not None and rows else None
    return result
