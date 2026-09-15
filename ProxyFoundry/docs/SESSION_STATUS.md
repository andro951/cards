# Integrated application status

The complete application is implemented under ProxyFoundry: local API and separate-origin renderer, persistent multi-deck workspace, protected v48 compiler, native template library/editor, artwork setup, card inspector, render grid, explicit paired orders, new-tab printer helper, backup/restore and original Card Tools utilities.

Verified CI milestone: commit c529f9e5ab9edb83508dedf5222301a47ed85316, run 35020843679, all 90 tests passed with no skips or failures. That run includes eight genuine upstream CardConjurer faces (creature, triome, legendary land, artifact creature, Esika/Bridge, Saga, planeswalker), a second native-render/cache roundtrip, real HTTP UI flows, and the actually installed MV3 helper transferring an exact multi-chunk ZIP to a new tab. The merchant editor is intercepted with a controlled fixture; no live order, payment or checkout occurs.

The final source adds independently tested mutable-custom-art refresh controls, a direct deck images-ZIP action, distribution manifest checking and startup documentation. The CI workflow reruns the full suite after release changes. See the latest Proxy Foundry CI run for the final exact revision and test count.

Four approved Card Tools files still match their original Git blob hashes byte-for-byte. No fonts, runtime caches, artwork library archives, private keys, or browser profiles are included in the distributed ZIP.

The supplied Windows BAT files are not executed by Linux CI. Live merchant UI changes and physical print alignment remain outside automated proof. Unsupported structural recipes require compatible custom templates rather than silent approximation. The user's optional land-library URL is not supplied and remains configurable, unset by default.
