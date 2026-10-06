# Renderer test fixture

`synthetic-gmapsupp.img` is a 12 KB Garmin IMG compiled with mkgmap from
`make_synthetic_osm.py`. The data is synthetic and authored for Terento's
tests: a hill with 20 m contour lines, two forest patches, a lake, a
secondary road, a path, a track, a peak, a hut, a village and a parking
place near 1.53° E, 42.51° N. It contains no OpenStreetMap or map-provider
data.

Regenerate it with:

```sh
python3 make_synthetic_osm.py synthetic.osm
java -jar mkgmap.jar --gmapsupp --family-id=7777 --product-id=1 \
  --description="Terento synthetic test" --route synthetic.osm
mv gmapsupp.img synthetic-gmapsupp.img
```
