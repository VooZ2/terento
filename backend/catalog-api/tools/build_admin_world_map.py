"""Generate local country SVG from Natural Earth 50m GeoJSON (public domain).
Usage: python tools/build_admin_world_map.py /path/to/ne_50m_admin_0_countries.geojson
Source: https://github.com/nvkelso/natural-earth-vector/tree/master/geojson
No runtime map service or dependency. Country boundaries are cartographic data.
"""
import hashlib
import html
import json
from pathlib import Path
import re
import sys

source = Path(sys.argv[1])
data = json.loads(source.read_text())
target = Path(__file__).resolve().parents[1] / 'src/terento_catalog/admin_world_map.py'
existing = target.read_text().split('WORLD_MAP_SVG =', 1)[0]
existing = existing.split('WORLD_MAP_COUNTRY_ALIASES.update', 1)[0]
existing = re.sub(r'^#.*\n', '', existing, flags=re.M).lstrip()
def simplify(points, tolerance=0.15):
    if len(points) < 4: return points
    # Iterative Douglas–Peucker in SVG coordinates; retain closed ring ends.
    keep = {0, len(points)-1}
    pending = [(0, len(points)-1)]
    while pending:
        start, end = pending.pop()
        ax, ay = points[start]; bx, by = points[end]
        dx, dy = bx-ax, by-ay; length = dx*dx+dy*dy
        farthest, distance = start, 0
        for i in range(start+1,end):
            px, py = points[i]
            t = max(0,min(1,((px-ax)*dx+(py-ay)*dy)/length)) if length else 0
            squared = (px-ax-t*dx)**2+(py-ay-t*dy)**2
            if squared>distance: farthest,distance=i,squared
        if distance>tolerance*tolerance:
            keep.add(farthest); pending.extend([(start,farthest),(farthest,end)])
    return [points[i] for i in sorted(keep)]

paths = {}
aliases = {}
for feature in data['features']:
    prop = feature['properties']
    code = str(prop.get('ISO_A2_EH') or prop.get('ISO_A2')).lower()
    if not re.fullmatch('[a-z]{2}', code) or code == 'aq':
        continue
    for key in ('ISO_A2', 'ISO_A3', 'ISO_A2_EH', 'ISO_A3_EH', 'NAME', 'NAME_LONG', 'ADMIN'):
        name = re.sub('[^A-Za-z0-9]', '', str(prop.get(key) or '')).upper()
        if name and name != '99': aliases[name] = code
    geometry = feature['geometry']
    polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
    commands = []
    for polygon in polygons:
        for ring in polygon:
            points = []
            for lon, lat in ring:
                xy = (round((lon+180)*2.5, 1), round((85-lat)*2.5, 1))
                if not points or xy != points[-1]: points.append(xy)
            points = simplify(points)
            if len(points) < 3: continue
            commands.append('M' + 'L'.join(f'{x:g},{y:g}' for x,y in points) + 'Z')
    paths.setdefault(code, []).extend(commands)
assert len(paths)>220
svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 365"><title>World installation coverage</title><desc>Natural Earth 50m country boundaries, public domain. Equirectangular projection.</desc>'+''.join(f'<path id="{code}" fill-rule="evenodd" d="{"".join(commands)}"/>' for code,commands in sorted(paths.items()))+'</svg>'
metadata = '# Natural Earth 50m countries, public domain.\n# Input SHA256: '+hashlib.sha256(source.read_bytes()).hexdigest()+'\n# Rebuild with tools/build_admin_world_map.py.\n'
target.write_text(metadata+existing+'WORLD_MAP_COUNTRY_ALIASES.update('+repr(aliases)+')\n\nWORLD_MAP_SVG = '+repr(svg)+'\n')
print(len(paths), 'country shapes;', len(svg), 'SVG bytes')
