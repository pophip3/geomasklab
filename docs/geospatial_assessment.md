# Optional GeoTIFF area assessment

The core evidence format reports pixel quantities. The optional geospatial
assessment adds physical-area assumptions and a georeferenced mask without
changing or overwriting that core record.

```sh
python -m pip install ".[geo]"
geomasklab geospatial evidence.zip matching-rgb.tif --method nominal --output area.zip
geomasklab verify-geospatial area.zip
```

`area.zip` contains exactly `evidence.zip`, `source.tif`, `mask.tif`,
`geospatial.json` and `manifest.json`. Verification checks membership and hashes,
replays core pixel evidence, rereads the source raster, recomputes areas and
compares the exported mask's pixels, dimensions, CRS and affine transform.
Regenerating hashes after changing a recorded area does not make it verify.

The packaged [geospatial JSON Schema](../src/geomasklab/schemas/geospatial-1.0.schema.json)
documents required fields, types, units and area-model alternatives. Export it with
`geomasklab schema geospatial`. Shape validation supplements numerical replay;
it does not replace it.

## Input contract

- An embedded GeoTIFF of at most 128 MiB, with an explicit CRS and stored affine
  transform. CRS definitions and axis units are read by Rasterio/PROJ, rather
  than inferred from file names or assumed to be metres.
- A one-band grayscale or three/four-band, unsigned 8-bit RGB raster, on the
  **exact** image grid stored in the verified evidence. The first three bands
  must reproduce its RGB pixels; grayscale is repeated into all three channels.
- All source bands/pixels must be valid. Nodata, masked pixels and transparent
  alpha require a separate domain contract and are rejected in this version.
- No resizing, reprojection, radiometric scaling or alignment is performed.
  The source raster's coordinate interpretation is an input assertion. Pixel
  equality binds it to the evidence but does not authenticate the raster producer.

The headless image limit is 64 million pixels. Use the explicit
[`render-raster` bands/window/scaling operation](raster_inputs.md) to prepare
multi-band or high-bit-depth rasters while retaining grid metadata.
Source-image rights continue to apply to an assessment containing the raster.

## Area models

| Method | Definition | Supported coordinates | Interpretation |
| --- | --- | --- | --- |
| `nominal` | `abs(a*e-b*d) * x_unit_to_m * y_unit_to_m` per affine cell | Projected CRS with declared finite linear-unit conversions | Square metres of projected coordinate cells; projection distortion is uncorrected |
| `geodesic` | Sum the absolute WGS84 geodesic area of each four-corner pixel polygon | EPSG:4326, EPSG:3857, WGS84 UTM EPSG:32601-32660 / 32701-32760 | Ellipsoid-surface corner model, with explicit XY transformation; row aggregation on axis-aligned EPSG:4326/3857 grids; general grids limited to 500,000 pixels |

Here `(a,b,c,d,e,f)` is the raster affine transform. Nominal area supports rotated
and sheared grids through the determinant. CRS units may be metres, feet or
US-survey feet; they are converted using declared CRS definitions. For example,
an EPSG:2263 coordinate-unit pixel is not silently treated as a square metre.
See [Rasterio CRS unit conversion](https://rasterio.readthedocs.io/en/stable/api/rasterio.crs.html).

For the geodesic method, corners are transformed using `always_xy=True`, then
measured with `pyproj.Geod(ellps="WGS84").polygon_area_perimeter`. All areas and
coordinates must be finite; invalid Earth coordinates and unsupported CRSs are
rejected. Raster edge curvature between corners, terrain elevation and slope
are omitted. A four-corner model is an approximation to the full raster footprint,
not a surveyed terrain area. See [the Geod API](https://pyproj4.github.io/pyproj/stable/api/geod.html).

Each record includes foreground, selected-region and whole-image area, in `m2`,
and two corresponding area-weighted coverage ratios. Pixel ratios remain in
the unchanged core bundle. Area-weighted and pixel-weighted ratios can differ
on latitude-dependent grids. Empty selected regions have null coverage.

## Mask export and reproducibility

`mask.tif` stores the **selected** positive/complement mask as unsigned 8-bit
0/255 values with the exact source CRS and affine transform. Background zero is
a valid class, not nodata. The TIFF includes the evidence ZIP's SHA-256 tag.

Physical replay compares floating-point areas within relative/absolute `1e-9`
tolerance; pixel counts and identities match exactly. Library versions are
recorded. Source software version is historical metadata, independently of the
current replay implementation. Hashes and replay do not establish semantic accuracy
or authenticity; self-consistent replacements remain possible.

`examples/geospatial_workflow.py` creates explicitly **synthetic** GeoTIFF fixtures
with known pixel sizes to check area conversion and exported-grid preservation.
The bundled NASA photograph has no georeference and is never assigned invented
coordinates. The [real 2019 NAIP case](../evaluation/geospatial/README.md) checks four polygon
domains and nominal areas against independently rasterized GDAL/Rasterio results.
Axis-aligned EPSG:4326/3857 geodesic areas reuse a longitude-invariant cell area
per row; other supported grids retain individual four-corner evaluation.
A small-grid brute-force Geod oracle tests row aggregation independently.
