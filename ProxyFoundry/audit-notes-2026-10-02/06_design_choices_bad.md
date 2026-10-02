# Design debt to replace carefully

- Replaced in chunks 1–2: global busy rejection, whole-job preparation draining,
  and unowned activity/cancellation. Further monolithic jobs remain to convert.
- Duplicate render-complete toast and deck-ready notification still appear;
  consolidate completion while retaining persistent notification during editing.
- Serial render → save → refresh can waste renderer idle time; benchmark bounded
  overlap and throttle refresh before choosing a production change.
- Runtime bundle no-store startup policy redownloads unchanged data; retain
  mixed-build validation while investigating version-keyed caching.
