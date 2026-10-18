# Popup dismissal review

Reviewed the popup paths in `site/` and the browser-specific modules in `web/`.
Backdrop clicks never dismiss a popup. Optional dialogs accept Esc and X;
successful actions and navigation controls can complete their dialogs. Redundant
Cancel, Done, and Not now dismiss buttons were removed; use Esc or the header X.
Native image and printing pickers use a dialog so Esc closes the top popup and
returns focus to the editor underneath it.

| Popup / flow | Dismissal policy |
| --- | --- |
| Custom artwork credits during generation | Required. No X or Cancel; Esc, direct close, and replacement are blocked. Continue validates all artists and saves them before closing. Preparation remains paused until then. |
| Match your artwork | Required. No X or Back to setup; finish every pairing or explicitly choose permitted Scryfall defaults. Finish closes after clearing the pairing checkpoint; a failure leaves the helper available to retry. |
| Add New Deck | Optional before submitting. Protected while reading/importing the manifest; failures unlock it. Choose Look is optional because no deck has been created yet. |
| Add cards, choose frame, artist credits by card, copy token | Optional editing. Existing validation controls applying changes; creating a token is protected while saving. |
| Card inspector and meld reverse editor | Optional. Save, generation and review downloads protect the editor; successful saves close it and failures restore dismissal. |
| Artwork, official rules and official flavor printing pickers | Optional nested dialogs. Esc/X affect only the picker. Applying a selection protects it until success or failure. |
| Enlarged card, artwork, tutorial and order images | Optional native dialogs. Esc/X only; no outside-click removal. |
| Create reusable style | Optional; protected while saving. |
| Choose decks for order | Optional; protected while calculating the order plan. |
| Order review and individual warning review | Optional inspection. Closing does not accept warnings. Building remains blocked until warnings are resolved. Browser ZIP packaging protects its dialog; legacy packaging intentionally closes before starting its background job. |
| Print package ready, print path, browser helper, deck ready, deletion explanation | Optional information/navigation. |
| Save artwork choices / Connect GitHub | Optional export. Existing saving guard prevents dismissal during writes; no GitHub update is required to generate images. |
| Select template face / source, create template, edit template | Optional authoring. Existing save validation stays enforced. Source/preview generation is cancellable when the editor closes. Saving an approved template is protected. |
| Original printing downloader / copy-token file exporter | Optional tools; protected during downloads/export. |
| Export Backup / Import from Backup | Optional selection. Submission closes the dialog intentionally before its owned background task starts. |
| Deleted deck preview / confirmation dialogs | Optional. Closing a confirmation declines the operation. |

The shared dialog lifecycle also prevents another popup from replacing a required
or busy dialog, retains the existing close callbacks and synchronous focus, and
keeps focus in the popup when its backdrop is clicked. Per-card artist save
retries retain the latest revision after any partial success.
