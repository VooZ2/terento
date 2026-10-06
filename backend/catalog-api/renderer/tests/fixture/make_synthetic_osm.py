"""Generate a small synthetic OSM file (no real OSM data) for renderer tests."""
import math, sys
LON0, LAT0 = 1.52, 42.50          # synthetic hill near the Pyrenees
SPAN = 0.024                       # ~2 km
nodes, ways = [], []
nid, wid = [1], [1]
def node(lon, lat, tags=None):
    i = nid[0]; nid[0] += 1
    nodes.append((i, lat, lon, tags or {})); return i
def way(ids, tags):
    i = wid[0]; wid[0] += 1
    ways.append((i, ids, tags)); return i
def ring(cx, cy, rx, ry, n=48, wob=0.0, ph=0.0):
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        f = 1 + wob * math.sin(3 * a + ph)
        pts.append(node(cx + rx * f * math.cos(a), cy + ry * f * math.sin(a)))
    return pts + [pts[0]]
cx, cy = LON0 + SPAN / 2, LAT0 + SPAN / 2
# contours: hill 1800 m base to 2300 m summit, every 20 m
for h in range(1820, 2300, 20):
    r = (2300 - h) / 500 * SPAN * 0.45
    tags = {"contour": "elevation", "ele": str(h)}
    tags["contour_ext"] = "elevation_major" if h % 100 == 0 else "elevation_minor"
    way(ring(cx, cy, r, r * 0.75, wob=0.08, ph=h / 50), tags)
way(ring(cx - SPAN * 0.3, cy - SPAN * 0.25, SPAN * 0.12, SPAN * 0.08, wob=0.15), {"landuse": "forest"})
way(ring(cx + SPAN * 0.32, cy - SPAN * 0.3, SPAN * 0.1, SPAN * 0.07, wob=0.1), {"landuse": "forest"})
way(ring(cx - SPAN * 0.35, cy + SPAN * 0.3, SPAN * 0.05, SPAN * 0.035), {"natural": "water", "name": "Test Lake"})
road = [node(LON0 + SPAN * t, LAT0 + SPAN * (0.1 + 0.05 * math.sin(t * 6))) for t in [i / 30 for i in range(31)]]
way(road, {"highway": "secondary", "name": "Valley Road", "ref": "T-1"})
village = node(LON0 + SPAN * 0.2, LAT0 + SPAN * 0.13, {"place": "village", "name": "Testville"})
path = [node(LON0 + SPAN * (0.2 + 0.3 * t), LAT0 + SPAN * (0.13 + 0.37 * t) + 0.002 * math.sin(t * 12)) for t in [i / 25 for i in range(26)]]
way(path, {"highway": "path", "sac_scale": "mountain_hiking", "name": "Summit Path"})
track = [node(LON0 + SPAN * (0.9 - 0.4 * t), LAT0 + SPAN * (0.1 + 0.3 * t)) for t in [i / 15 for i in range(16)]]
way(track, {"highway": "track", "tracktype": "grade2"})
node(cx, cy, {"natural": "peak", "name": "Test Peak", "ele": "2300"})
node(LON0 + SPAN * 0.42, LAT0 + SPAN * 0.42, {"tourism": "alpine_hut", "name": "Test Hut"})
node(LON0 + SPAN * 0.22, LAT0 + SPAN * 0.11, {"amenity": "parking"})
out = ['<?xml version="1.0" encoding="UTF-8"?>', '<osm version="0.6" generator="terento-synthetic">',
       f'<bounds minlat="{LAT0}" minlon="{LON0}" maxlat="{LAT0 + SPAN}" maxlon="{LON0 + SPAN}"/>']
for i, lat, lon, tags in nodes:
    if tags:
        out.append(f'<node id="{i}" version="1" lat="{lat:.7f}" lon="{lon:.7f}">')
        out += [f'<tag k="{k}" v="{v}"/>' for k, v in tags.items()]
        out.append('</node>')
    else:
        out.append(f'<node id="{i}" version="1" lat="{lat:.7f}" lon="{lon:.7f}"/>')
for i, ids, tags in ways:
    out.append(f'<way id="{i}" version="1">')
    out += [f'<nd ref="{n}"/>' for n in ids]
    out += [f'<tag k="{k}" v="{v}"/>' for k, v in tags.items()]
    out.append('</way>')
out.append('</osm>')
open(sys.argv[1], 'w').write('\n'.join(out) + '\n')
