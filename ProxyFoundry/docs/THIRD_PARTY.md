# Components and attribution

Proxy Foundry integrates the user's approved Card Tools v58 source, preserved in `vendor/card_tools`. Its native template assets and original project notices remain in those files.

The browser renderer uses CardConjurer files from `Investigamer/cardconjurer`, pinned to commit `2fcddba8966156d484cedf54d8214996748dd5e1`. Missing image assets may be fetched from `d1rtyskittl3z/Card-Cipherist`, commit `47087b3fc21e2cef61c58b9ebf180968ee991658`, under `public/`. These runtime code, frame, and font files are downloaded individually as needed. No CardConjurer repository archive, Station script, or font files are distributed in the application ZIP.

Scryfall supplies card/printing metadata and art URLs. Card illustrations and artist credits remain attributable to their original artists and rights holders. Custom artwork is supplied by the user. This application does not assert ownership of third-party artwork or imply affiliation with Scryfall, Wizards of the Coast, CardConjurer, or TCGPlaytest.

Pillow is the image processing dependency. pytest and Playwright are development/test dependencies. Their packages retain their respective upstream license notices when installed. Proxy Foundry does not need Node or Playwright for normal use.

The Station module is fetched individually from `joshbirnholz/cardconjurer` at commit `d3c6706692898d596ec6a5be0be44f63062c9e12`, verified against SHA-256 `481c2be522fc10089e75aa6281aace9e88e345868330948dd64705edb9314c21`. That file is byte-for-byte identical to the module previously fetched from `cardconjurer.app`. The raw GitHub endpoint permits cross-origin browser requests; the original site endpoint does not. Its rendering functions are unchanged; a checked UI property assignment replaces its single eval-based assignment in memory, and the existing core composites its native canvases in the required order. The GitHub fork has no repository license file, so no blanket redistribution license is claimed for its code or assets. Confirm upstream permissions before redistributing any CardConjurer files.

To update the Station module, pin a new upstream commit and SHA-256 in `foundry/domain.py`, then run the Station security, static website, and native Station rendering tests. If the module's UI assignment changes, update the small in-memory adapter in `foundry/runtime.py` after reviewing that change. The application contains no Station source copy to sync.
