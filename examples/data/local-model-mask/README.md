# Retained local-model mask

`mask.png` is an actual RemoteSAMv1 prediction from the credited, public-domain
NAIP image at `../naip-denver/image.png`, with referring prompt `all buildings`.
It has 6,543 foreground pixels. `provenance.json` records input/output hashes,
fixed source/checkpoint identity, inference parameters and package versions.

Run `python examples/replay_model_mask.py` from the repository root to verify
the hashes, count independent pixel scopes and export four evidence ZIPs.
No inference, model download or remote service occurs during that replay.
These records do not establish authenticated model origin or semantic accuracy.
Image credit: USDA-FSA-APFO / USGS The National Map; see the NAIP data provenance.
