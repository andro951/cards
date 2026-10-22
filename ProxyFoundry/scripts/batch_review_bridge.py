"""Loopback-only file bridge for the browser workspace's opt-in review action."""
import json
import re
import secrets
import threading
import urllib.parse

from foundry.developer_batch_review import DeveloperBatchReview, MAX_UPLOAD_CHUNK
from foundry.domain import ConflictError, ValidationError


class BrowserDecks:
    def __init__(self):
        self.decks = {}

    def update(self, decks):
        if not isinstance(decks, list) or len(decks) > 500:
            raise ValidationError("Invalid batch deck manifest.")
        for deck in decks:
            if not isinstance(deck, dict) or not re.fullmatch(r"[-a-f0-9]{36}", str(deck.get("id", ""))):
                raise ValidationError("Invalid batch deck ID.")
            if not isinstance(deck.get("name"), str) or not deck["name"] or len(deck["name"]) > 500:
                raise ValidationError("Invalid batch deck name.")
            if type(deck.get("revision")) is not int or deck["revision"] < 1:
                raise ValidationError("Invalid batch deck revision.")
            summary = deck.get("summary")
            if not isinstance(summary, dict) or type(summary.get("faces")) is not int or not 0 <= summary["faces"] <= 20000:
                raise ValidationError("Invalid batch deck face count.")
        self.decks.update({deck["id"]: deck for deck in decks})

    def list_decks(self):
        return list(self.decks.values())

    def deck(self, ident):
        if ident not in self.decks:
            raise ValidationError("The browser deck is not in this batch.")
        return self.decks[ident]


class BatchReviewBridge:
    def __init__(self, app_root):
        self.token = secrets.token_urlsafe(32)
        self.workspace = BrowserDecks()
        self.service = DeveloperBatchReview(app_root, self.workspace)
        self.jobs = {}
        self._control_lock = threading.Lock()

    def handle(self, handler):
        parsed = urllib.parse.urlsplit(handler.path)
        if not parsed.path.startswith("/dev-batch-review/"):
            return False
        try:
            origin = "http://127.0.0.1:" + str(handler.server.server_port)
            if handler.headers.get("Host") != origin.removeprefix("http://"):
                raise PermissionError("Use the preview's loopback address.")
            if handler.headers.get("Origin", origin) != origin or handler.headers.get("Sec-Fetch-Site") == "cross-site":
                raise PermissionError("Cross-site batch access is not allowed.")
            path = parsed.path.removeprefix("/dev-batch-review")
            if handler.command == "GET" and path == "/availability":
                return self.respond(handler, {"available": self.service.available(), "token": self.token})
            if not secrets.compare_digest(handler.headers.get("X-BPF-Batch", ""), self.token):
                raise PermissionError("Reload the preview before starting a review batch.")
            if handler.command == "GET":
                job = self.jobs.get(path.removeprefix("/jobs/")) if path.startswith("/jobs/") else None
                if not job:
                    raise ValidationError("This batch job is no longer available.")
                return self.respond(handler, dict(job))
            if handler.command != "POST":
                raise ValidationError("Unsupported batch request.")
            match = re.fullmatch(r"/([-a-f0-9]{36})/upload/([-a-f0-9]{36})", path)
            if match:
                query = urllib.parse.parse_qs(parsed.query)
                offset = int(query.get("offset", [""])[0])
                return self.respond(handler, self.service.upload_chunk(match[1], match[2], offset, self.body(handler, MAX_UPLOAD_CHUNK)))
            data = json.loads(self.body(handler, 2 * 1024 ** 2))
            if not isinstance(data, dict):
                raise ValidationError("Expected a batch request object.")
            if path == "/start":
                # The engine stays in the browser; only deck identities/statuses cross this bridge.
                with self._control_lock:
                    self.service._expire_sessions()
                    if self.service._lock.locked():
                        raise ConflictError("A review batch is already running.")
                    self.workspace.decks = {}
                    self.workspace.update(data.get("decks"))
                    result = self.service.start(data.get("deckIds"))
                return self.respond(handler, result)
            match = re.fullmatch(r"/([-a-f0-9]{36})/(ready|upload/start|upload/complete|commit|abort)", path)
            if not match:
                raise ValidationError("Unknown batch action.")
            session, action = match.groups()
            if action == "ready":
                current = self.service._session(session)
                ids = {deck["id"] for deck in current["decks"]}
                if not isinstance(data.get("decks"), list) or any(deck.get("id") not in ids for deck in data["decks"]):
                    raise ValidationError("That deck is not in this review batch.")
                with current["mutex"]:
                    self.service._editable(current)
                    self.workspace.update(data["decks"])
                return self.respond(handler, {"ok": True})
            if action == "upload/start":
                return self.respond(handler, self.service.begin_upload(session, data.get("deckId"), data.get("filename"), data.get("bytes"), data.get("revision")))
            if action == "upload/complete":
                return self.respond(handler, self.service.finish_upload(session, data.get("deckId")))
            if action == "abort":
                return self.respond(handler, self.service.abort(session))
            # One commit per session: reserve before dispatching so a second POST cannot race it.
            with self._control_lock:
                if session in self.jobs:
                    raise ConflictError("Comparison is already in progress.")
                job = {"state": "running", "message": "Starting ImageFolderCompareAll", "done": 0, "total": 0}
                self.jobs[session] = job
            def run():
                def progress(done, total, message):
                    job.update(done=done, total=total, message=message)
                try:
                    result = self.service.commit(session, progress)
                    job.update(state="done", result=result)
                except Exception as error:
                    job.update(state="failed", error=str(error))
            threading.Thread(target=run, name="batch-review-checker", daemon=True).start()
            return self.respond(handler, {"id": session})
        except PermissionError as error:
            return self.respond(handler, {"error": str(error)}, 403)
        except ConflictError as error:
            return self.respond(handler, {"error": str(error)}, 409)
        except (ValidationError, ValueError, TypeError, KeyError) as error:
            return self.respond(handler, {"error": str(error)}, 400)
        except Exception as error:
            return self.respond(handler, {"error": "The local batch operation failed: " + str(error)}, 500)

    def body(self, handler, limit):
        if handler.headers.get("Transfer-Encoding"):
            raise ValidationError("Chunked requests are not supported.")
        size = int(handler.headers.get("Content-Length", "0"))
        if not 0 < size <= limit:
            raise ValidationError("Invalid batch upload size.")
        handler.connection.settimeout(90)
        raw = handler.rfile.read(size)
        if len(raw) != size:
            raise ValidationError("The batch upload was interrupted.")
        return raw

    def respond(self, handler, value, status=200):
        raw = json.dumps(value).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)
        return True
