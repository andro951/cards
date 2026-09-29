# Design debt to address during feature work

- The same visible “token” result has two compilation pipelines. One is assembled in `compiler.build_token_data`; another is applied later by the vendored copy-token tool. Styling fixes can land in one path and miss the other. Add a shared final token presentation stage at the app boundary.
- Nickname metadata implicitly chooses visual framing. This makes it hard to offer an independent Godzilla template choice, especially separate land and non-land choices. Keep the metadata field but represent frame selection explicitly.
- `site/setup.js` builds a large Art & setup page as one template literal with inline handlers. A visual picker will be easier to maintain as a focused module and modal component, using the existing modal utilities.
- `compiler.py` combines semantic extraction, dozens of special frame adapters, art placement and cache decisions. Keep new frame policy narrowly scoped with named helpers and versioned template identity.
- The vendored token converter mutates compiled output after the main compiler's final formatting and cache key. App-specific final treatment belongs after that conversion, with a new final render key.
