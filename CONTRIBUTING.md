# Contributing

GeoMaskLab maintains a deliberately bounded version 1.0 feature scope. Discuss
changes through the repository issue tracker before adding dependencies or
extending the documented area models, adding model training or multi-user hosting.

## Development checks

Use the separate Python 3.10-3.12 evaluation environment in
[Reproduction environments](docs/reproduction_environments.md). Its fixed
requirements include schema, geospatial, provenance, signing, plotting and the
Label Studio brush converter. After installing that environment, run:

```sh
python -m unittest discover -s tests -p "test_*.py" -q
python reviewer_demo.py
python evaluation/run_integrity_matrix.py
python examples/recalculate_region.py reviewer-output/right.zip
```

Keep basic startup and the reviewer workflow dependent only on Pillow. The
research CI checks the complete optional lock on Windows and Linux with Python
3.10 and 3.12. Its minimal environment also runs on Windows, Linux and macOS
with Python 3.13.

Write comments, docstrings, messages and documentation in clear English. New
examples must use English requests. Legacy input-language compatibility and
verbatim historical observations are distinct from generated application text.
Add meaningful behavior tests for new scientific operations, failure handling,
artifact identity or evidence compatibility. Do not report simulated transports
as model inference or procedural masks as real-image accuracy evidence.

## Evidence compatibility

Retain the `geoscope-evidence/1.0` identifier for compatible existing bundles.
Do not alter frozen evaluation records or silently rewrite imported observations.
New fields should have documented units/denominators and independent verifier
checks. A derived result must preserve source prediction identity, start pending
review and distinguish new local processing from historical inference.

Keep inputs, weights, credentials, private endpoints and runtime outputs outside
Git. Attribute external methods and comply with their separate licenses. Describe
the final behavior and its validation in a contribution; avoid unsupported
accuracy, speed, novelty or adoption claims.
