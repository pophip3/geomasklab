# Observed handoff-study protocol

`python examples/prepare_handoff_study.py` prepares real NAIP inputs for a small
matched-information, counterbalanced study. Its output contains participant
materials, an administrator-only answer key, protocol and an empty response CSV.
Preparing those files does not constitute an experiment: observed participants
and generated observations remain zero.

Recruit 3–5 voluntary colleagues after checking applicable ethics/privacy
requirements. Use anonymous participant IDs. Each participant completes two
cases under different conditions: loose source/measurement files and a portable
evidence ZIP. Both conditions contain the same scientific information. Alternate
the condition order across participants; keep the answer key from participants.
Record prior familiarity, actual tools, elapsed time and each response. Allow
equivalent local Python/GIS tools and retain all failures.

The task is to reproduce foreground pixels, both denominators and both ratios,
and determine whether the region derivation called a model. For actual collected
responses, run:

```sh
python evaluation/analyze_handoff_study.py workflow-output/handoff-study/observations.csv --answer-key workflow-output/handoff-study/administrator-answer-key.json --output study-results.json
```

The analyzer rejects an empty CSV, duplicate responses, missing identities and
invalid timing. It scores recorded responses against the prepared answer key
and produces descriptive error rates and median times by condition. Rounding
tolerance for ratios is relative `1e-4`/absolute `1e-6`. Task order and raw responses
must be retained. Convenience participants cannot establish population-wide
productivity gains, and familiarity/learning can confound results.

No colleagues have participated in this repository's current preparation. There
are no claimed error rates, completion times or human-impact findings yet.
