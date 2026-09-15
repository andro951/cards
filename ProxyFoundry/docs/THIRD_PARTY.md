# Components and attribution

Proxy Foundry integrates the user's approved Card Tools v58 source, preserved in `vendor/card_tools`. Its native template assets and original project notices remain in those files.

The browser renderer is the actual CardConjurer code from `Investigamer/cardconjurer`, pinned to commit `2fcddba8966156d484cedf54d8214996748dd5e1`. Missing image assets may be resolved from `d1rtyskittl3z/Card-Cipherist`, commit `47087b3fc21e2cef61c58b9ebf180968ee991658`, under `public/`. Runtime code, frames and fonts are downloaded individually at runtime; no CardConjurer repository archive or font files are distributed in the application ZIP. Upstream notices and applicable asset permissions remain with their respective authors.

Scryfall supplies card/printing metadata and art URLs. Card illustrations and artist credits remain attributable to their original artists and rights holders. Custom artwork is supplied by the user. This application does not assert ownership of third-party artwork or imply affiliation with Scryfall, Wizards of the Coast, CardConjurer, or TCGPlaytest.

Pillow is the image processing dependency. pytest and Playwright are development/test dependencies. Their packages retain their respective upstream license notices when installed. Proxy Foundry does not need Node or Playwright for normal use.

The Station module is fetched individually from `https://cardconjurer.app/js/frames/versionStation.js`, verified against SHA-256 `481c2be522fc10089e75aa6281aace9e88e345868330948dd64705edb9314c21`. This module is not present in the older pinned GitHub core. Its rendering functions are unchanged; a checked UI property assignment replaces its single eval-based assignment, and the existing core composites its native canvases in the required order. No copy of the module is distributed in the application ZIP.
