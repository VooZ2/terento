"""Display-only labels. Never use these strings for identity matching or storage."""
import re

SIZE = r'\b\d{2,3}(?:\s*[x×]\s*\d{2,3})?\s*mm\b'
FEATURE = r'\b(?:AMOLED|MicroLED|MIP|Solar|inReach)\b'
SEPARATORS = ' ,·•|:–—-'


def _clean(value):
    return ' '.join(str(value or '').replace('®', '').replace('™', '').split())


def _size(value):
    text = str(value)
    if text.casefold().endswith('mm'):
        text = text[:-2].rstrip()
    parts = text.replace('×', 'x').replace('X', 'x').split('x')
    return ' × '.join(part.strip() for part in parts) + ' mm'


def model_label(value):
    label = re.sub(r'^Garmin\s+', '', _clean(value), flags=re.I)
    label = re.sub(SIZE, '', label, flags=re.I)
    label = re.sub(FEATURE, '', label, flags=re.I)
    label = re.sub(r'\bHistorical\s*$', '', label, flags=re.I)
    label = re.sub(r'\b(?:fenix|fēnix)\b', 'fēnix', label, flags=re.I)
    label = re.sub(r'\bpro\b', 'Pro', label, flags=re.I)
    label = re.sub(r'(fēnix\s+\d+)([sx])\b', lambda m: m[1] + m[2].upper(), label, flags=re.I)
    label = re.sub(r'[·•|:,]+', ' ', label)
    return _clean(label).strip(SEPARATORS)


def variant_label(row):
    """Order only supplied facts; missing/false flags do not imply features."""
    raw = _clean(row.get('variant'))
    model = _clean(row.get('model'))
    if re.search(r'\bHistorical\s*$', model, re.I):
        return 'Historical'
    source = raw + ' ' + model
    size = row.get('caseSizeMm', row.get('case_size_mm'))
    sizes = re.findall(SIZE, source, re.I)
    parts = [f'{size} mm'] if isinstance(size, int) and not isinstance(size, bool) and size > 0 else []
    if not parts and sizes:
        parts.append(_size(sizes[0]))
    display = row.get('screenTechnology') or row.get('screen_technology') or row.get('displayType') or row.get('display_type') or ''
    source += ' ' + str(display)
    screens = {name for name in ('AMOLED', 'MicroLED', 'MIP') if re.search(r'\b' + name + r'\b', source, re.I)}
    for name in ('AMOLED', 'MicroLED', 'MIP', 'Solar', 'inReach'):
        if name in screens and len(screens) > 1:
            continue
        present = re.search(r'\b' + name + r'\b', source, re.I)
        if name == 'Solar':
            present = present or row.get('solar') is True
        if name == 'inReach':
            present = present or row.get('inReach', row.get('inreach')) is True
        if present:
            parts.append(name)
    extras = re.sub(FEATURE, '', re.sub(SIZE, '', raw, flags=re.I), flags=re.I)
    for extra in re.split(r'[,·•|/]', extras):
        extra = _clean(extra).strip(SEPARATORS)
        if extra and extra not in parts:
            parts.append(extra)
    return ', '.join(parts)
