# System design and behavior map

## Runtime and ownership

This is a local Python and browser application. `run.py` selects the workspace and starts the loopback HTTP service in `foundry/server.py`. `site/index.html` loads `site/app.js`, which routes a deck library, deck studio, templates, orders, settings and help pages. There is no authored build step for the site. `requirements.txt` lists Pillow; the legacy Card Tools pipeline is vendored under `vendor/card_tools`.

`foundry/storage.py` keeps deck, template, order and settings documents in SQLite with revisions, assets by SHA-256, and current face renders as named PNGs. Revision checks prevent an old browser tab from silently replacing a newer deck. The workspace lives outside the extracted application folder. Render cache identity combines compiled card data, source art, renderer commit, pipeline version and template version (`domain.render_key`). Each prepared face receives a deck/face scoped key in `workspace._prepare_card_faces`.

## Input and preparation

`site/deck.js` imports Scryfall deck URLs, JSON exports and card lists through `Sources.import_deck`; exact printing IDs and multi-face information are retained. `site/setup.js` holds a draft of Art & setup. It selects Scryfall art, a GitHub art folder or local art files; symbols, back, template rules, credits, flavor policy and deck-wide token conversion are also configured there. Saving sends the draft and any staged card metadata to `Workspace.save`; generating then prepares faces and renders them.

There is one implemented `data.json` path: `site/github-setup.js` calls `/api/setup/github-import` for a public project folder. `foundry/github_setup.py` lists its root, optionally downloads `data.json`, validates schema v1, and returns a complete settings patch plus `cardData`. The browser stages that result; `Workspace._apply_card_data` merges nonempty nicknames and flavor text into every matching face when the deck is saved. Exact face names are required. Empty values do not clear overrides. The GitHub artwork field in Art & setup reads images from an `art/` directory; it does not fetch `data.json`. No separate local `data.json` upload or direct GitHub `data.json` link is implemented.

`Workspace.prepare` refreshes selected Scryfall metadata, resolves art and flavor policy, chooses each face's template and invokes `Compiler.compile_face`. The compiler builds semantic card fields, selects a native Card Tools recipe or a saved custom template, applies art placement and text/frame transformations, then emits CardConjurer data. Face errors are recorded rather than replacing a broken layout with a plausible wrong one. Scryfall tokens have a dedicated `build_token_data` path. Copy tokens and the deck-wide token option instead run the vendored `make_copy_tokens.build_token` *after* normal compilation; that operation changes the frame list and some text geometry.

## Templates, Godzilla treatment and typography

Template rules are grouped by `domain.type_group`: ordinary, land, legendary land, basic land, token, planeswalker, DFC faces and other structural groups. Built-ins are Automatic, Classic card, Full-art land and Crowned full art (`compiler.BUILTINS`). `site/setup.js` currently renders one select menu per present group. `site/templates.js` is a separate page for creating or uploading custom CardConjurer templates and mapping text slots. The cards drawn on that page are CSS placeholders, not live sample renders.

Scryfall `flavor_name` or a saved `semanticOverrides.nickname` activates `apply_nickname_treatment` automatically. It places the nickname in the top line and the true name beneath. Ordinary groups append a complete M15 nickname frame and P/T piece when available, plus a title or crown with empty masks. Special groups usually retain their structural frame and add only the top name treatment; planeswalkers and approved modal DFCs retarget native nickname assets. Colorless ordinary cards have no complete nickname frame source in `_nickname_frame_src`, so they receive only a colorless title/crown addon. The code applies this treatment regardless of the template choice, after universal frame color processing.

The native Scryfall token builder makes a broad-art Token Regular frame, with masked frame components, and positions title, type and rules. Its title is set white, while type and rules retain the inherited colors because those fields are not assigned color or outline in `build_token_data`. The vendored copy-token converter replaces all frame layers with its M15 token frame and sets title color to `#fde367`; it does not revise type/rules colors or preserve a prior nickname frame layer. These are distinct rendering paths and need separate visual tests.

## Native rendering and output

`site/render.js` asks the server for a plan, starts a separate-origin iframe and sends compiled card data to `site/runtime-bridge.js`. `foundry/runtime.py` fetches individual CardConjurer scripts and assets from pinned sources; the browser bridge calls the real native `loadCard` and canvas renderer, then uploads PNG blobs through a render session. The server checks expected image size before saving. Completed cards remain cached if later faces fail.

`foundry/orders.py` pairs each physical front and back explicitly and writes `FRONT/000001.png` and `BACK/000001.png` into an immutable order ZIP. `extension/` is an optional MV3 helper for TCGPlaytest transfer, with batch support; it does not control checkout. `foundry/backup.py` exports/restores workspace documents and referenced images. Settings also exposes diagnostics and generated-image deletion.

## Trust boundaries

The local server uses exact loopback Host checks, CSRF on mutations, origin checks and a separate renderer origin. `Network` validates remote URLs, bounds downloads and caches them. GitHub bundle import builds raw URLs from validated repository paths, checks folder shape and stages the result before deck save. Custom templates are validated but still depend on native renderer behavior, so a real render and print proof remain the final visual checks.
