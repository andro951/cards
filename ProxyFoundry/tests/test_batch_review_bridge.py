"""The preview bridge is opt-in, same-origin and independent of browser storage."""
import functools
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from scripts.static_server import StaticSiteServer, BatchPreviewHandler
from scripts.batch_review_bridge import BatchReviewBridge


@pytest.fixture
def bridge(tmp_path):
    root = tmp_path / "ProxyFoundry";root.mkdir()
    checker = tmp_path / "ImageFolderCompareAll" / "ImageFolderCompareAll.exe"
    checker.parent.mkdir();checker.write_bytes(b"fixture")
    (tmp_path / "alpha" / "cards").mkdir(parents=True)
    server = StaticSiteServer(("127.0.0.1", 0), functools.partial(BatchPreviewHandler, directory=str(root)))
    server.batch_review_bridge = BatchReviewBridge(root)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = "http://127.0.0.1:" + str(server.server_port)
    def request(path, data=None, headers=None):
        body = json.dumps(data).encode() if data is not None else None
        req = Request(origin + "/dev-batch-review" + path, data=body, headers=headers or {})
        try:
            response = urlopen(req)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)
    yield server.batch_review_bridge, request, origin
    server.shutdown();server.server_close()


def test_preview_requires_same_origin_and_unguessable_request_token(bridge):
    value, request, origin = bridge
    status, available = request("/availability")
    assert status == 200 and available["available"] and available["token"]
    assert request("/start", {"deckIds": []})[0] == 403
    headers = {"X-BPF-Batch": available["token"], "Origin": "https://other.example"}
    assert request("/start", {"deckIds": []}, headers)[0] == 403
    assert request("/availability", headers={"Host": "hostile.example"})[0] == 403
    assert not value.service._sessions


def test_preview_accepts_only_selected_browser_decks_and_aborts_staging(bridge):
    value, request, origin = bridge
    headers = {"X-BPF-Batch": request("/availability")[1]["token"], "Origin": origin}
    ident = "11111111-1111-4111-8111-111111111111"
    deck = {"id": ident, "name": "Alpha", "status": "prepared", "printStatus": "prepared", "summary": {"faces": 1}, "revision": 1}
    status, started = request("/start", {"decks": [deck], "deckIds": [ident]}, headers)
    assert status == 200
    session = started["id"]
    assert request("/start", {"decks": [deck], "deckIds": [ident]}, headers)[0] == 409
    assert request("/" + session + "/ready", {"decks": [{**deck, "id": "22222222-2222-4222-8222-222222222222"}]}, headers)[0] == 400
    assert request("/" + session + "/ready", {"decks": [{**deck, "status": "ready", "printStatus": "ready"}]}, headers)[0] == 200
    assert request("/" + session + "/abort", {}, headers)[0] == 200
    assert not value.service._sessions
    assert not list(value.service.cards_root.glob(".proxyfoundry-batch-review-*"))
