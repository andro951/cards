# Design debt to replace carefully

- One boolean for every task conflates unload protection with resource conflicts.
- Whole-job draining prevents menu API reads from running between saved cards.
- One shared activity handler lacks ownership when tasks overlap.
- Serial render → save → refresh can waste renderer idle time; benchmark bounded
  overlap and throttle refresh before choosing a production change.
- Runtime bundle no-store startup policy redownloads unchanged data; retain
  mixed-build validation while investigating version-keyed caching.
