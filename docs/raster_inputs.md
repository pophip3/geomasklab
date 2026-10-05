# Raster windows, radiometric rendering and resource limits

The measurement core processes an explicit 8-bit RGB image and a binary mask.
For a larger, 16-bit or multiband local GeoTIFF, select the RGB bands, pixel window
and value range before measurement. The optional renderer makes those decisions
explicit and preserves the window's CRS and affine transform.

```sh
python -m pip install ".[geo]"
geomasklab render-raster multispectral.tif --bands 3 2 1 --window 100 200 1024 1024 --value-range 0 10000 --output rendered
geomasklab segment rendered/image.png --provider exg --output candidates.png
geomasklab create --image rendered/image.png --mask candidates.png --target vegetation --source "Explicitly rendered color baseline" --aligned --output evidence.zip
geomasklab geospatial evidence.zip rendered/source.tif --output area.zip
```

Band indexes are one-based and their order is explicitly RGB. A window is
`column,row,width,height` in stored raster pixels. No reprojection, resampling or
automatic nodata filling occurs. Selected pixels must be finite and valid. uint8
can retain its values directly; other types require a finite `LOW < HIGH` common
range. Scaling clips to that range, maps to 0–255 and rounds half up. The number
of clipped values is recorded.

`rendering.json` records the source's streaming SHA-256/byte length, original
dimensions/types, band indexes, window, scaling, CRS, transform and output identities.
The original large raster remains external; preserve this preparation receipt
alongside it. It is not automatically embedded as the source raster of a core
bundle. The verified geospatial assessment binds the actual rendered GeoTIFF to
the exact RGB image that was measured.

## Separate runtime limits

| Operation | Limit |
| --- | --- |
| Headless image/mask grid | 64,000,000 pixels |
| Headless encoded image / binary mask | 48 MB / 32 MB |
| Core evidence ZIP and total expanded encoded members | 192 MB |
| Matching GeoTIFF source | 128 MB |
| Geospatial/zonal ZIP and expanded members | 384 MB |
| Browser image upload | 16,000,000 pixels and 12 MB |
| Browser mask/evidence upload | 12 MB |
| General transformed geodesic corner grid | 500,000 pixels |
| Axis-aligned EPSG:4326/3857 geodesic grid | Headless grid/file limits; one area calculation per row |

MB denotes multiples of 1,024² bytes. Limits are ceilings, not guaranteed throughput
or memory requirements. The core retains RGB image/overlay and binary grids in
memory; a large run can require substantially more memory than its encoded inputs.
Use explicit windows for larger scenes. High-entropy RGB PNGs can reach archive
limits before reaching the pixel ceiling. Connected-component measurement remains
Python-based and can dominate foreground-heavy runs.

Row acceleration applies only when longitude translation preserves the per-cell
ellipsoidal corner area: axis-aligned geographic or Web Mercator grids. The grid
must remain in the unwrapped longitude domain and span less than 180 degrees.
WGS84 UTM, rotation/shear and other supported general grids retain per-pixel
transformation with the smaller ceiling. No unsupported row approximation is applied.
