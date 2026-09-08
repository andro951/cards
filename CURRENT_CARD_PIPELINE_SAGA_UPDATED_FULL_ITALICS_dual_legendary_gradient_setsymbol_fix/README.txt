CURRENT CARD PIPELINE + TIME LORDS RUN

The Scryfall deck wrapper now hard-excludes:
- Sideboard
- Outside the Game
- Maybeboard

Scryfall currently exports "Outside the Game" as the JSON key "outside".
The wrapper excludes both "outside" and "outside_the_game".

TIME LORDS LIVE EXPORT
- Commanders: 1 included
- Lands: 40 included
- Nonlands: 59 included
- Maybeboard: 6 excluded
- Outside the Game: 85 excluded
- Sideboard: absent / 0
- Playable selected cards: 100

PIPELINE
Semantic generation succeeded for all 100 cards, producing 101 Card Conjurer
faces because Esika, God of the Tree // The Prismatic Bridge has two faces.

Saga support is now wired in for the six approved reference layouts used by:
- An Unearthly Child
- The Girl in the Fireplace
- Trial of a Time Lord
- Death in Heaven
- The Eleventh Hour
- The Day of the Doctor

`timelords_FULL.cardconjurer` is the full no-auto-fit compile of the complete
Time Lords deck, including all six Sagas.

For future batches, Sagas whose chapter grouping does not match one of the
approved reference layouts will still compile, but they will be flagged as
unchecked in a sidecar report named like:
`<output>_FLAGGED_UNCHECKED_SAGAS.json`

Other unsupported special frames still fail normally instead of being guessed.

timelords_SUPPORTED_ONLY.cardconjurer remains in the package as the earlier
95-face diagnostic compile from before Saga support was finished.

This package also contains all current code, exact live deck export/cache,
run manifests/logs, and the current Derevi and Doctor Who artifacts.


SAGA STATUS (2026-09-02)
------------------------
The compiler now automatically builds Sagas.
Approved/reference behavior currently includes:
- normal-card horizontal title geometry
- type line at Saga Y position
- set symbol X 1737 px, Y 2400 px
- art bounds X 1005, Y 316, W 854, H 2041
- exact-size Saga art target: 854 x 2041 px
- standard Card Conjurer cover/center-crop auto-fit equation
- approved checked layouts for the six reference Sagas above
- unchecked sidecar reporting for new/unmatched Saga layouts
