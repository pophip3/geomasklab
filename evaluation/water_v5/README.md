# Reproduce the 65-scene water V5 assessment

This directory runs the water V5 checkpoint used for Section 3.4 of the manuscript.
It checks the exact source-raster hashes, performs inference and compares TP, FP
and FN for each of the 65 scenes with the archived experiment.

## Obtain the inputs

1. Download `GeoMaskLab_Water_V5_Checkpoint.zip` from the
   [reproduction release](https://github.com/pophip3/geomasklab/releases/tag/v1.0.0-repro.20261016)
   and extract it. Its `model.safetensors` SHA-256 is
   `ef86d7d5c4e1b9c30762f72a5435b59efe2da917e5a04a9b2364bf977a85596e`.
2. Obtain [OpenEarthMap imagery and labels](https://zenodo.org/records/7223446)
   from the official provider. `scene_manifest.json` lists the 65 filenames,
   regions and SHA-256 values. Keep the provider's `images` and `labels` folders.
3. Download the official [SAM ViT-H checkpoint](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth).
   SHA-256: `a7bf3b02f3ebf1267aba913ff637d9a2d5c33d3173bb679e46d9f338c26f262e`.

## Install

The checked inference environment uses Python 3.9.25, PyTorch 2.6.0 and CUDA 12.4.
Create a separate virtual environment, activate it, then run:

```sh
python -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
python -m pip install -r evaluation/water_v5/requirements.txt
```

## Run

From the source repository root:

```sh
python evaluation/water_v5/reproduce_water_v5.py --weights /path/to/model.safetensors --sam-checkpoint /path/to/sam_vit_h_4b8939.pth --data-root /path/to/OpenEarthMap --output output/water-v5 --device cuda:0
```

Use paths to the actual downloaded files on Windows as well as Linux/macOS.
The script writes a predicted PNG for each scene and `results.json`.

Expected aggregate counts: **TP 1,356,978; FP 35,782; FN 256,701**.
Expected metrics: **IoU 82.27%; Dice 90.27%; precision 97.43%; recall 84.09%**.
`all_scene_counts_match: true` confirms that every scene agrees with the record.
The source checks and checkpoint checks stop execution if a different input is supplied.

## Recorded inference procedure

The UNet uses an EfficientNet-B4 encoder, SCSE decoder attention, nine output
classes, RGB / 255 input scaling and water class 6. Native-grid 512 x 512 tiles
overlap with a stride of 256 pixels. Four quarter-turn predictions are averaged
per tile, merged with a Hann window clipped at 0.05, then thresholded at 0.5.
SAM ViT-H refines the boundary using automatically selected water/non-water
points, while preserving both semantic interiors. `refinement.py` retains the
recorded refiner implementation. This assessment uses the V5 checkpoint;
the current interactive backend can select a later checkpoint independently.

## Attribution

Base model: [OpenEarthMap](https://open-earth-map.org/code.html), by Junshi Xia,
Naoto Yokoya, Bruno Adriano and Clifford Broni-Bediako.
Architecture: [segmentation_models.pytorch](https://github.com/qubvel-org/segmentation_models.pytorch).
Boundary model: [Segment Anything](https://github.com/facebookresearch/segment-anything).
Dataset image and label terms follow the [OpenEarthMap source attribution](https://open-earth-map.org/attribution.html).
GeoMaskLab evaluation code is MIT licensed; dataset and upstream model terms
remain associated with their respective materials.
