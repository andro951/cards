# Checkpoint · 15 September 2026

Recovered every previously committed source file through the scoped CI source artifact, without downloading the repository's artwork tree. Added the missing runnable HTTP API and separate-origin renderer server. Added portable image/deck/template backups (font and runtime caches excluded), CSRF/Host checks, render-session authorization and bounded ZIP range downloads for the print helper. 74 local Python tests currently pass, including seven real-loopback API tests. The three initially failing tests were a stale Room classification expectation, a missing empty-deck constructor, and a template regression assertion that did not normalize the two intentional asset transport URLs. No v48 source files were edited.

UI modules, full print-helper content script and live browser rendering are the next integration work. This checkpoint is not a release.
