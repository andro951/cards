# Design choices to preserve

- Stage GitHub setup results in the browser and apply only on save. Import failure does not partially alter a deck (`github_setup.py`, `site/github-setup.js`).
- Match `data.json` entries by exact face name, validate schema/size and reject unknown nonempty names before saving (`parse_card_data_json`, `Workspace._apply_card_data`).
- Keep Scryfall exact printings and face structure; report unsupported layouts rather than silently drawing an ordinary frame (`Sources`, `Compiler.compile_face`).
- Use the native pinned CardConjurer renderer and cache complete size-checked PNGs (`Runtime`, `render.js`, `Workspace.save_render`).
- Scope template invalidation and preserve completed render/order snapshots (`Compiler.template_identity`, `Workspace`, `Orders`).
- Keep front/back pairing explicit by shared numbered filenames (`Orders.build`).
- Use workspace revisions, loopback/CSRF boundaries and a separate renderer origin (`Store.put`, `Handler.guard`).
