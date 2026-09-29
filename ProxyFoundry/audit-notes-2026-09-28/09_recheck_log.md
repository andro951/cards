# Recheck log

- 2026-09-28: Started from clean `main` at `b7aa734`; no application source changes made in this review.
- Re-read the import UI, `data.json` validator, save merger, compiler nickname/token paths, vendored token converter, render bridge and order writer before documenting interactions.
- `python -m compileall -q foundry run.py` passed using the included virtual environment.
- `node --check` passed for each `site/*.js` file.
- `scripts/verify_vendor.py` failed on committed `pipeline/card_data_to_cardconjurer.py` blob mismatch (expected `0bc9c2a...`, actual `53786dcc...`).
- `pytest` unavailable in both the included virtual environment and system Python; no unit/browser/native test result claimed.
- No live Scryfall/GitHub/TCP request or CardConjurer PNG render was run. Visual symptom explanations remain code-backed hypotheses where marked.
