# Bulk Proxy Forge regression and requirements audit

Date: 2026-09-30. Reviewed main at `e237b64`. Investigation only: no application or test changes.

## Comparison points

- `b7aa734`: original source audit and original local application.
- `11b4975`: improved local Python application before the browser conversion. This is the most useful working baseline, since it includes initial Godzilla fixes and test grouping.
- `e237b64`: current static website, after the browser response-memory fix.

Inputs: both Downloads redesign documents, subsequent user instructions in this conversation, existing September 28 audit, Git history, current source, historical diagnostics ZIPs, and browser diagnostics JSON. Later user instructions override earlier documents. Cosmetic wording changes are excluded from the major-change analysis.

Start with [major changes](11_major_changes.md), [bugs](03_bugs.md), and [recommendations](07_improvement_plan.md). The remaining files document requirements, architecture, evidence, and limitations.

The recent failure around 80/100 cards is not root-caused by the supplied logs. Confirmed architectural problems are distinguished from plausible scale and recovery risks. An earlier fix is not declared ineffective merely because an older ZIP contains the same historical error.

## Verification

A direct BrowserJobs probe confirmed that the operation finishes before start returns its job ID. One real static-website smoke test failed in 23.30 seconds because it expects distinct generated frame previews; current identical card-back placeholders are explicitly requested. The test stops before its later render/review/ZIP checks. No full suite was run, and the failing assertion was left unchanged.
