# Requirements checklist

Current evidence: **yes**, **no**, or **needs render**.

| Requirement | State | Evidence |
| --- | --- | --- |
| One-click GitHub project import discovers root `data.json` | Yes | `github_setup.import_github_setup` |
| Upload `data.json` directly in Art & setup | No | `site/setup.js`, `server.py` |
| Supply a direct GitHub `data.json` link | No | GitHub art field indexes images only |
| Stage imported nicknames/flavor until Save | Yes | `github-setup.js`, `Workspace.save` |
| Exact face-name matching and schema validation | Yes | `parse_card_data_json`, `_apply_card_data` |
| Independently choose Godzilla land and non-land frames | No | `BUILTINS`, `templateOptions` |
| Show rendered examples in frame picker | No | Current group select menus |
| Use complete frame pieces for ordinary nickname treatment | Yes in data; needs render | `apply_nickname_treatment` |
| Preserve complete Godzilla frame through token conversion | No | `make_copy_tokens.apply_token_layout` replaces frames |
| White, black outlined type/rules/flavor on full-art token | No in current data; needs render | `build_token_data`, vendored converter |
| Respect special card structures | Mostly, needs case review | `type_group`, compiler special paths |
| Cache/render only complete PNGs, pair order fronts/backs | Yes | `save_render`, `Orders.build` |
