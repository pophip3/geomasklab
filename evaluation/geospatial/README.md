# Real NAIP zonal consistency check

Run `python examples/naip_zonal_workflow.py` with the optional geo extra.
The frozen input tile is USDA NAIP `m_3910417_nw_13_060_20190803`, acquired in
Colorado on 3 August 2019, exported by USGS on an explicit EPSG:32613 RGB grid.
[Input rights, source identities and processing](../../examples/data/naip-denver/README.md)
are retained with the example.

GeoMaskLab uses its own pixel-center scanline rasterizer. The comparison path
projects the supplied GeoJSON vertices with PyProj, rasterizes with Rasterio/GDAL
`all_touched=False`, and directly counts decoded binary pixels with NumPy.
Both paths use the same supplied coordinate model and nominal projected-area
definition. This checks implementation consistency; it is not independent
survey validation, semantic accuracy or a human-efficiency experiment.

| Study region | Foreground pixels, both paths | Region pixels, both paths | Nominal area, both paths (m2) | Difference (m2) |
| --- | ---: | ---: | ---: | ---: |
| west-plot | 65,910 | 109,968 | 23,727.60 | 0 |
| east-with-exclusion | 53,512 | 110,160 | 19,264.32 | 0 |
| union-plots | 23,939 | 45,600 | 8,618.04 | 0 |
| slanted-plot | 17,062 | 42,361 | 6,142.32 | 0 |

See [consistency.csv](consistency.csv) and [summary.json](summary.json) for exact
floating-point values and both coverage denominators. These regions are
analyst-defined demonstrations, not official parcel/administrative boundaries.
The color-baseline mask is unvalidated vegetation-candidate input. No projection
distortion or terrain correction is included in nominal area. QGIS was not run;
the measured comparator is Rasterio/GDAL and NumPy.
