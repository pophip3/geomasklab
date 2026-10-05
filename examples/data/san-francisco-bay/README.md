# Real-image example: San Francisco Bay

`image.png` is an aspect-preserving, 337 × 512 pixel derivative of NASA astronaut
photograph **ISS004-E-10288**, captured on 21 April 2002. Credit: NASA/Johnson
Space Center, Earth Sciences and Image Analysis Laboratory.

- [NASA source and image download](https://science.nasa.gov/earth/earth-observatory/san-francisco-bay-2474/)
- [NASA image and media usage guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/)
- `provenance.json`: download identity, derivative dimensions, processing and asset hashes.

The photograph is distributed here for a factual educational software example
under NASA's media guidelines, with attribution. NASA has not endorsed or
validated this software. The project MIT license does not relicense the photograph.

`mask.png` is a precomputed **RGB green-color candidate baseline**, using integer
Otsu thresholding of `2*G-R-B`. Its exact algorithm and threshold are recorded in
`mask.png.provider.json`. The mask can be regenerated without model weights or
network access. It includes false positives and omissions; it is neither human
annotation nor validated tree/vegetation ground truth. It must not be used to
claim semantic accuracy or real geographic area. The photograph has no CRS or
pixel ground resolution in this example.

Run `python examples/real_image_handoff.py` from the source checkout. It checks
the packaged assets, reproduces the mask, creates whole-image and right-half
evidence, then writes verified standalone HTML reports. The same right-half
foreground numerator gives **20.7199% of the whole image** and **41.3173% of the
selected right half**. This demonstrates explicit denominator reporting.
