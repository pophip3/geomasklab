# Retained expected procedural-example results

`summary.json` is a committed expected-output record produced by `examples/reproduce_example.py`. It is retained for comparison and provenance, rather than as a temporary runtime artifact.

From the repository root, run:

```sh
python examples/reproduce_example.py
```

This deterministic procedural example checks the foreground counts 75,350 (whole), 37,350 (right), 38,000 (left) and 12,850 (selected ROI). It regenerates `summary.json` and verified ZIP exports in this directory. Generated ZIPs are ignored by Git.

These are illustrative demo outputs, not fresh model-inference results or the current NAIP Figure 4 measurements. In particular, `semantic_accuracy_verified: false` and `origin_authenticated: false` are intentional scope labels. See the root README's **Reproduce paper results** section and `docs/reproduce_paper_results.md` for the current manuscript workflows and data requirements.

The checked-in numerical record is preserved without editing its values.
