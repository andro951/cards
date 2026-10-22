"""Actual app entry point, shared worker exports, upload routes and local comparison."""
import io
import os
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from playwright.sync_api import expect, sync_playwright

from foundry.server import App, LocalServer, Handler
from scripts.batch_review_bridge import BatchReviewBridge
from foundry.storage import Store
from foundry.network import Network
from foundry.domain import PIPELINE_VERSION, uid
from foundry.images import ingest_image
from foundry.workspace import DEFAULT_SETTINGS
from foundry.developer_batch_review import DeveloperBatchReview

pytestmark = pytest.mark.skipif(os.environ.get("PF_BROWSER") != "1", reason="Opt-in real Chromium batch test")
ROOT = Path(__file__).resolve().parents[1]


def png(color):
    output = io.BytesIO()
    Image.new("RGB", (200, 280), color).save(output, "PNG")
    return output.getvalue()


@pytest.mark.parametrize("preview", [False, True], ids=["legacy", "browser-preview"])
@pytest.mark.parametrize("failure", [None, "export", "checker"])
def test_library_batch_uses_workers_and_preserves_baselines_on_failure(tmp_path_factory, monkeypatch, failure, preview):
    tmp_path = tmp_path_factory.mktemp("br")
    app_root = tmp_path / "Cards" / "ProxyFoundry"
    app_root.mkdir(parents=True)
    cards = app_root.parent / "alpha" / "cards"
    cards.mkdir(parents=True)
    output = app_root.parent / "ImageFolderCompareAll"
    output.mkdir()
    checker = output / "ImageFolderCompareAll.exe"
    checker.write_bytes(b"test only")
    previous_result = output / "diff" / "alpha" / "previous.png"
    previous_result.parent.mkdir(parents=True)
    previous_result.write_bytes(b"previous result")
    raw = png("green")
    store = Store(tmp_path / "workspace")
    app = App(store, Network(store, transport=lambda url: (raw, "image/png", {})))
    asset = ingest_image(store, raw)
    store.render_put("fixture-render", asset)
    template_key, template_version, _ = app.ws.compiler.template_identity("standard", "auto")
    face = {"id": uid(), "name": "Bird", "compiled": {"renderKey": "fixture-render", "generationVersion": PIPELINE_VERSION,
            "templateKey": template_key, "templateVersion": template_version}}
    card = {"id": uid(), "name": "Bird", "quantity": 1, "faces": [face], "scryfall": {
        "name": "Bird", "layout": "normal", "image_uris": {"png": "https://cards.scryfall.io/test.png"}}}
    deck = store.put("decks", {"name": "Alpha", "settings": dict(DEFAULT_SETTINGS, backAsset=asset["id"]),
                              "status": "prepared", "cards": [card]})
    ready = {"value": False}
    def list_decks():
        rows = app.ws.list_decks()
        if not ready["value"]:
            for row in rows:
                row.update(status="prepared", printStatus="prepared")
        return rows
    workspace = SimpleNamespace(list_decks=list_decks, deck=app.ws.deck, review_download_file=app.ws.review_download_file)
    entered, release = threading.Event(), threading.Event()
    calls = []
    monkeypatch.syspath_prepend(str(ROOT.parent / "ImageFolderCompareAll"))
    import compare_all
    def run(args, **kwargs):
        calls.append(args)
        entered.set()
        assert release.wait(15), "checker fixture was not released"
        if failure == "checker":
            return SimpleNamespace(returncode=1, stdout="fixture checker failed", stderr="")
        report = []
        compared = compare_all.run_all(app_root.parent, output, emit=report.append)
        return SimpleNamespace(returncode=int(bool(compared.failed)), stdout="\n".join(report), stderr="")
    app.developer_batch_review = DeveloperBatchReview(app_root, workspace, checker=checker, process_runner=run)
    plan = app.ws.review_plan(deck["id"])
    old_zip = cards / "approved.zip"
    with zipfile.ZipFile(old_zip, "w") as archive:
        for item in plan["items"]:
            image = Image.new("RGB", (201, 140), "black")
            data = io.BytesIO(); image.save(data, "PNG")
            archive.writestr(item["filename"], data.getvalue())
    old_bytes = old_zip.read_bytes()
    bridge = BatchReviewBridge(app_root)
    bridge.service.process_runner = run
    server = LocalServer(app)
    if preview:
        class PreviewHandler(Handler):
            def dispatch(self, mutating):
                if not bridge.handle(self):
                    super().dispatch(mutating)
        server.RequestHandlerClass = PreviewHandler
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            errors, downloads, generation = [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("download", lambda download: downloads.append(download))
            # Keep rendering deterministic; the actual shared export workers and all save/commit routes run unchanged.
            page.route("**/site/render.js", lambda route: route.fulfill(content_type="text/javascript", body="""
                export async function renderDecks(ids,options) {
                    if(options.force) throw Error('Unexpected forced rerender');
                    await fetch('/__test_render');return {};
                }
                export const renderCard=()=>{},renderTemplatePreviews=()=>{},renderTemplateSource=()=>{},renderTemplateModel=()=>{};
            """))
            page.route("**/__test_render", lambda route: generation.append(route))
            page.route("https://cards.scryfall.io/**", lambda route: route.fulfill(
                status=404 if failure == "export" else 200, content_type="image/png", body=raw))
            if preview:
                def bootstrap(route):
                    response = route.fetch()
                    value = response.json(); value["browser"] = True
                    route.fulfill(response=response, json=value)
                def decks_route(route):
                    response = route.fetch(); rows = response.json()
                    if not ready["value"]:
                        for row in rows:
                            row.update(status="prepared", printStatus="prepared")
                    route.fulfill(response=response, json=rows)
                page.route("**/api/bootstrap", bootstrap)
                page.route("**/api/decks", decks_route)
            page.goto(server.origin)
            batch = page.get_by_role("button", name="Temporary batch review", exact=True)
            expect(batch).to_be_visible()
            expect(batch).to_be_enabled()
            page.locator('[data-select="' + deck["id"] + '"]').check()
            with page.expect_request("**/__test_render"):
                batch.click()
            page.evaluate("true")
            page.wait_for_function("() => document.querySelector('[aria-label=\"Deck library actions\"] button:last-child').disabled")
            expect(page.locator("#render-selected")).to_be_disabled()
            assert len(generation) == 1
            ready["value"] = True
            generation[0].fulfill(status=200, body="ok")
            if failure != "export":
                expect(page.locator("#activity-detail")).to_contain_text("Running ImageFolderCompareAll", timeout=15000)
                assert entered.is_set(), errors
                expect(batch).to_be_disabled()
                expect(page.locator("#render-selected")).to_be_disabled()
                expect(page.locator("#activity-cancel")).to_be_disabled()
                release.set()
            if failure:
                expect(page.locator("#toast-host")).to_contain_text("HTTP 404" if failure == "export" else "previous ZIPs are unchanged", timeout=15000)
                assert previous_result.read_bytes() == b"previous result"
                assert list(cards.glob("*.zip")) == [old_zip]
            else:
                expect(page.get_by_role("dialog")).to_contain_text("Changed: 1", timeout=15000)
                assert len(list(cards.glob("*.zip"))) == 2
                saved = next(path for path in cards.glob("*.zip") if path != old_zip)
                with zipfile.ZipFile(saved) as archive:
                    assert archive.testzip() is None
                    image = Image.open(io.BytesIO(archive.read(plan["items"][0]["filename"])))
                    assert image.size == (201, 140)
                assert not previous_result.exists()
                page.locator("#modal-close").click()
            expect(batch).to_be_enabled()
            expect(page.locator("#render-selected")).to_be_enabled()
            assert len(calls) == (0 if failure == "export" else 1)
            assert old_zip.read_bytes() == old_bytes
            assert downloads == []
            assert not errors, errors
            browser.close()
    finally:
        release.set()
        server.shutdown(); server.server_close(); app.close()
