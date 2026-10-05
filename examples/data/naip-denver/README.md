# Denver NAIP geospatial example

This is a real 512 x 512 RGB chip from USDA NAIP, distributed by USGS The
National Map. Catalog tile `m_3910417_nw_13_060_20190803` was acquired on
3 August 2019 in Colorado. Credit: USDA-FSA-APFO / USGS The National Map.

The [USGS NAIP dataset description](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-national-agriculture-imagery-program-naip)
identifies its public-domain source/usage. Dataset DOI:
[10.5066/F7QN651G](https://doi.org/10.5066/F7QN651G). The imagery's terms are
separate from the project's MIT code license.

`source.tif` is the original downloaded service-exported GeoTIFF, with a locked
catalog item and nearest-neighbor interpolation. The service reprojected the
source NAD83 imagery to WGS84 UTM zone 13N (EPSG:32613). Its 0.6 m output grid
is recorded exactly in `provenance.json`; these are exported-grid measurements,
not claims that source tile bytes or surveyed ground areas are unchanged.

`image.png` retains exactly those RGB pixels. `mask.png` is an excess-green/Otsu
color baseline, with its parameters in the sidecar. It demonstrates measurement
and replay; it is neither a manual reference mask nor established tree accuracy.
`zones.geojson` contains four analyst-defined study regions, including holes,
overlapping MultiPolygon components and a slanted polygon. They are not official
park, parcel or administrative boundaries.

Run `python examples/naip_zonal_workflow.py` with the optional geo extra. It
generates physical-area packets and an independently computed Rasterio/NumPy
consistency table. All required data are local; no account or network is needed.
