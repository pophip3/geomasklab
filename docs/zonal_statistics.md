# Polygon and GeoJSON zonal assessment

GeoMaskLab measures each feature independently against a verified source mask.
The original evidence ZIP remains unchanged. The zonal packet binds the exact
geometry bytes, rasterization rule, resulting domains and both coverage denominators.

```sh
geomasklab zonal evidence.zip pixel-zones.json --coordinates pixel --output zones.zip
geomasklab verify-zonal zones.zip

python -m pip install ".[geo]"
geomasklab zonal evidence.zip zones.geojson --coordinates wgs84 --raster source.tif --output geographic-zones.zip
```

## Coordinate and topology contract

`pixel` coordinates use GeoJSON-shaped Polygon/MultiPolygon structures in the
EXIF-normalized image grid. They are explicitly pixel geometries, rather than
RFC 7946 geographic GeoJSON. `wgs84` follows RFC 7946 longitude/latitude order
and requires a GeoTIFF whose RGB pixels exactly match the evidence. Legacy
`crs` members, invalid latitude/longitude and antimeridian crossings are rejected.

WGS84 vertices are transformed to the raster CRS and inverse affine pixel grid.
Edges remain straight between transformed vertices; they are not densified along
geodesics. Densify curved or large geographic boundaries externally and document
that preparation. This operation supports local study regions and does not claim
survey-grade boundary accuracy.

Each ring must be closed, finite and simple, with 4–257 positions. Self-crossing,
self-touching, backtracking and zero-area rings are rejected. Holes must lie
strictly inside the exterior; touching, crossing, overlapping or nested holes
are rejected. Up to 16 components per MultiPolygon and 15 holes per Polygon are
supported. A document contains 1–32 features and at most 4,096 positions/1 MB.
IDs are unique ASCII identifiers of up to 64 characters.

## Rasterization and denominators

The domain uses pixel centers `(column + 0.5, row + 0.5)`. An even-odd scanline
rule fills rings with half-open edge handling: a point exactly on a left/lower
scanline intersection is included; its right/upper counterpart is excluded.
Horizontal edges do not introduce duplicate crossings. Holes subtract from
their own component. MultiPolygon components are **unioned**, so overlapping
components are counted once within that feature, including inputs whose component
overlap would violate a strict OGC MultiPolygon topology convention.

Every domain is intersected with the source evidence's selected scope. Foreground
is the recorded positive/complement mask within that intersection. Each row reports
foreground pixels, selected-region pixels, whole-image pixels and both coverage
ratios. An empty zone has zero foreground and null within-region coverage.
Features are independent: overlapping features can each count the same pixel;
their reported areas must not be summed as a union.

With a matching projected GeoTIFF, nominal `m2` equals the cell affine determinant
times both declared axis-unit conversions times the counted pixels. Projection
distortion, terrain and mask semantic accuracy remain outside that quantity.
Zonal physical area currently uses this nominal model; it does not silently
substitute the optional geodesic assessment model.

## Packet and verification

The `geomasklab-zonal-assessment/1.0` packet contains source `evidence.zip`,
`zones.geojson`, `zonal.json`, an optional `source.tif`, numbered domain/foreground
PNG pairs and `manifest.json`. Files are bounded, unique and flat. Verification
checks hashes, replays the core bundle, transforms the exact supplied geometry,
reconstructs every domain, and compares pixels and measurements. Extra files,
modified masks and rehashed false measurements are rejected. Creator identity
and source-coordinate assertions require separate trust.

The [real NAIP example](../examples/data/naip-denver/README.md) compares four
domains with Rasterio/GDAL `all_touched=False` and direct NumPy counts. Its vertices
avoid exact center/edge ties. Rasterizers can differ on those ties; the explicit
GeoMaskLab rule remains the definition for its packet. The comparison is numerical
workflow validation, not a claim of new segmentation performance or faster GIS.

References: [RFC 7946](https://www.rfc-editor.org/rfc/rfc7946),
[Rasterio feature rasterization](https://rasterio.readthedocs.io/en/stable/topics/features.html).
