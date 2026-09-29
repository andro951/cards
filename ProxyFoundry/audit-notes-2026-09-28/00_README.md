# Proxy Foundry source review — 2026-09-28

Scope: `ProxyFoundry/` in the local `cards` repository, with the repository root and its `STYLE_RULES.md` used for context. Snapshot: clean `main` at `b7aa734` before these notes were written. These notes describe the original state. The subsequent implementation in this checkout addresses the data.json import, Godzilla template, frame picker, token rendering, and vendor verification findings; consult the current source for their updated behavior.

Read `01_system_design_document.md` for the behavior map, `02_source_map_and_interactions.md` for navigation, `03_bugs.md` and `04_issues_and_risks.md` for findings, then `07_improvement_plan.md` and `08_requirements_checklist.md` for the next implementation pass. Findings marked *static* need a real native render to verify their visual effect.
