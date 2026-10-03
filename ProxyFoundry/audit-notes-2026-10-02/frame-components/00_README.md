# Frame component audit — 2026-10-02

Scope: every built-in frame family and all recognized card groups in Bulk Proxy Forge. Production source is unchanged. Source snapshot: main, starting at 7c2e653.

Read [01_system_design_document.md](01_system_design_document.md) for the matrix, [03_bugs.md](03_bugs.md) for confirmed gaps and [07_improvement_plan.md](07_improvement_plan.md) for repair sequencing. JSON evidence records compiled probes and upstream component names; no upstream JavaScript is retained.

Checked 38 synthetic final compiler outputs (not rendered PNGs), the local frame builders, and 28 live upstream frame packs. Sixteen existing universal-color tests passed. No complete visual verification is claimed.
