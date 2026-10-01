# Choices to change

1. Emulating the old HTTP application in the browser without preserving asynchronous job semantics. API compatibility alone does not preserve user behavior.
2. Synchronizing the entire image-heavy workspace through Python memory. This changes old filesystem operations into browser allocation/synchronization costs.
3. Treating missing compilation as a global upgrade and removing the last visible render on edits. This increases work and weakens review.
4. Silent workspace fallback on permission loss. Storage identity must be visible and stable.
5. Exposing editor actions for template families the model rejects, and treating a single rendered preview as broad template approval.
6. Relying primarily on local-server tests to validate a browser-only product, with a stale real production smoke gate.
7. Routing/control complexity without durable ownership, version synchronization, timeouts and recovery checkpoints.

These findings support targeted architecture repair. They do not justify reverting the requested visual redesign, restoring a hosted server, or abandoning the existing renderer.
