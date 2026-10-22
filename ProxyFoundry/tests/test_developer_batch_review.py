from pathlib import Path
import json
import zipfile

import pytest

from foundry.developer_batch_review import DeveloperBatchReview
from foundry.domain import ConflictError, ValidationError


class Workspace:
    def __init__(self, root, decks):
        self.root = root
        self.decks = decks

    def list_decks(self):
        return [dict(deck) for deck in self.decks]

    def deck(self, deck_id):
        return next(dict(deck) for deck in self.decks if deck["id"] == deck_id)

    def review_download_file(self, token, filename):
        return self.root / "review-downloads" / f"{token}_{filename}"


def make_zip(path, contents=b"image"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("card_review.png", contents)
    return path


def setup(tmp_path, decks):
    for deck in decks:
        deck.setdefault("summary", {"faces": 2})
        deck.setdefault("revision", 1)
    app_root = tmp_path / "ProxyFoundry"
    app_root.mkdir()
    checker = tmp_path / "ImageFolderCompareAll" / "ImageFolderCompareAll.exe"
    checker.parent.mkdir()
    checker.write_bytes(b"fixture")
    for deck in decks:
        (tmp_path / deck["name"].lower() / "cards").mkdir(parents=True)
    workspace = Workspace(tmp_path / "workspace", decks)
    service = DeveloperBatchReview(app_root, workspace, checker=checker, process_runner=lambda *args, **kwargs: None)
    return service, workspace, checker


def export(workspace, deck_id, filename="BulkProxyForge_Review_Images_Deck_1234abcd.zip", *, valid=True):
    token = "11111111-1111-1111-1111-111111111111"
    source = workspace.review_download_file(token, filename)
    if valid:
        make_zip(source)
    else:
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"not a zip")
    return token, filename


def test_only_explicit_regeneration_statuses_are_eligible(tmp_path):
    decks = [
        {"id": "draft", "name": "Draft", "status": "draft", "printStatus": "draft", "summary": {"faces": 2}},
        {"id": "prepared", "name": "Prepared", "status": "prepared", "printStatus": "prepared"},
        {"id": "ready", "name": "Ready", "status": "ready", "printStatus": "ready"},
        {"id": "attention", "name": "Attention", "status": "attention", "printStatus": "attention"},
        {"id": "empty", "name": "Empty", "status": "draft", "printStatus": "draft", "summary": {"faces": 0}},
        {"id": "tokens", "name": "Tokens", "status": "prepared", "printStatus": "tokens-not-ready"},
    ]
    service, _, _ = setup(tmp_path, decks)
    assert [deck["id"] for deck in service.eligible()] == ["draft", "prepared"]
    with pytest.raises(ConflictError, match="status changed"):
        service.start(["empty"])


def test_exports_are_staged_until_all_succeed_then_checker_runs_once(tmp_path):
    decks = [{"id": "a", "name": "Alpha", "status": "prepared"},
             {"id": "b", "name": "Beta", "status": "prepared"}]
    service, workspace, checker = setup(tmp_path, decks)
    old = tmp_path / "alpha" / "cards" / "approved.zip"
    old.write_bytes(b"approved")
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        assert (tmp_path / "alpha" / "cards" / "BulkProxyForge_Review_Images_Alpha_1234abcd.zip").exists()
        assert old.read_bytes() == b"approved"
        return type("Result", (), {"returncode": 0, "stdout": "all-check completed", "stderr": ""})()

    service.process_runner = run
    session = service.start(["a", "b"])
    workspace.decks[0]["status"] = "ready"
    workspace.decks[0]["printStatus"] = "ready"
    filename = "BulkProxyForge_Review_Images_Alpha_1234abcd.zip"
    token, _ = export(workspace, "a", filename)
    service.stage_review(session["id"], "a", token, filename)
    with pytest.raises(ValidationError, match="Not every selected deck"):
        service.commit(session["id"])
    assert not list((tmp_path / "alpha" / "cards").glob("BulkProxyForge_Review_Images_*.zip"))
    assert calls == []

    workspace.decks[1]["status"] = "ready"
    workspace.decks[1]["printStatus"] = "ready"
    filename_b = "BulkProxyForge_Review_Images_Beta_1234abcd.zip"
    token_b, _ = export(workspace, "b", filename_b)
    service.stage_review(session["id"], "b", token_b, filename_b)
    result = service.commit(session["id"])
    assert result["decks"] == 2
    assert result["report"] == "all-check completed"
    assert len(calls) == 1
    assert calls[0][0] == [str(checker), "--no-pause"]
    assert (tmp_path / "alpha" / "cards" / filename).is_file()
    assert (tmp_path / "beta" / "cards" / filename_b).is_file()
    assert old.read_bytes() == b"approved"
    assert not list(tmp_path.glob(".proxyfoundry-batch-review-*"))


def test_failed_or_invalid_export_never_replaces_old_zip_or_runs_checker(tmp_path):
    decks = [{"id": "a", "name": "Alpha", "status": "prepared"}]
    service, workspace, _ = setup(tmp_path, decks)
    old = tmp_path / "alpha" / "cards" / "approved.zip"
    old.write_bytes(b"approved")
    calls = []
    service.process_runner = lambda *args, **kwargs: calls.append(args)
    session = service.start(["a"])
    workspace.decks[0]["status"] = "ready"
    workspace.decks[0]["printStatus"] = "ready"
    filename = "BulkProxyForge_Review_Images_Alpha_1234abcd.zip"
    token, _ = export(workspace, "a", filename, valid=False)
    with pytest.raises((zipfile.BadZipFile, ValidationError)):
        service.stage_review(session["id"], "a", token, filename)
    service.abort(session["id"])
    assert old.read_bytes() == b"approved"
    assert calls == []
    assert not list((tmp_path / "alpha" / "cards").glob("BulkProxyForge_Review_Images_*.zip"))


def test_duplicate_batch_start_is_rejected_without_touching_inputs(tmp_path):
    decks = [{"id": "a", "name": "Alpha", "status": "prepared"}]
    service, _, _ = setup(tmp_path, decks)
    session = service.start(["a"])
    with pytest.raises(ConflictError, match="already running"):
        service.start(["a"])
    service.abort(session["id"])

def test_status_change_before_commit_keeps_all_exports_staged(tmp_path):
    decks = [{"id": "a", "name": "Alpha", "status": "prepared"}]
    service, workspace, _ = setup(tmp_path, decks)
    old = tmp_path / "alpha" / "cards" / "approved.zip"
    old.write_bytes(b"approved")
    calls = []
    service.process_runner = lambda *args, **kwargs: calls.append(args)
    session = service.start(["a"])
    workspace.decks[0]["status"] = "ready"
    workspace.decks[0]["printStatus"] = "ready"
    filename = "BulkProxyForge_Review_Images_Alpha_1234abcd.zip"
    token, _ = export(workspace, "a", filename)
    service.stage_review(session["id"], "a", token, filename)
    workspace.decks[0]["status"] = "draft"
    workspace.decks[0]["printStatus"] = "draft"
    with pytest.raises(ConflictError, match="status changed"):
        service.commit(session["id"])
    assert old.read_bytes() == b"approved"
    assert not (tmp_path / "alpha" / "cards" / filename).exists()
    assert calls == []
    service.abort(session["id"])


def test_checker_failure_keeps_previous_result_and_existing_zip(tmp_path):
    decks = [{"id": "a", "name": "Alpha", "status": "prepared"}]
    service, workspace, checker = setup(tmp_path, decks)
    old = tmp_path / "alpha" / "cards" / "approved.zip"
    old.write_bytes(b"approved")
    old_result = checker.parent / "diff" / "alpha" / "old.png"
    old_result.parent.mkdir(parents=True)
    old_result.write_bytes(b"previous comparison")
    calls = []
    service.process_runner = lambda *args, **kwargs: (
        calls.append(args) or type("Result", (), {"returncode": 1, "stdout": "comparison failed", "stderr": ""})()
    )
    session = service.start(["a"])
    workspace.decks[0]["status"] = "ready"
    workspace.decks[0]["printStatus"] = "ready"
    filename = "BulkProxyForge_Review_Images_Alpha_1234abcd.zip"
    token, _ = export(workspace, "a", filename)
    service.stage_review(session["id"], "a", token, filename)
    with pytest.raises(ValidationError, match="previous comparison results were kept"):
        service.commit(session["id"])
    assert old.read_bytes() == b"approved"
    assert not (tmp_path / "alpha" / "cards" / filename).exists()
    recovered = list(tmp_path.glob(".proxyfoundry-batch-review-*"))
    assert len(recovered) == 1 and (recovered[0] / filename).is_file()
    assert old_result.read_bytes() == b"previous comparison"
    assert len(calls) == 1
    assert service.abort(session["id"]) == {"ok": True}

    # Recovery files survive the frontend's idempotent abort, and the lock is released.
    workspace.decks[0]["status"] = "prepared"
    service.abort(service.start(["a"])["id"])
    assert recovered[0].is_dir()


def ready_upload(tmp_path):
    decks = [{"id": "a", "name": "Alpha", "status": "prepared"}]
    service, workspace, checker = setup(tmp_path, decks)
    session = service.start(["a"])["id"]
    workspace.decks[0].update(status="ready", printStatus="ready")
    filename = "BulkProxyForge_Review_Images_Alpha_1234abcd.zip"
    source = make_zip(tmp_path / "source.zip").read_bytes()
    return service, workspace, session, filename, source


def test_browser_chunks_are_ordered_complete_and_revision_checked(tmp_path):
    service, workspace, session, filename, raw = ready_upload(tmp_path)
    service.begin_upload(session, "a", filename, len(raw), 1)
    with pytest.raises(ConflictError, match="offset"):
        service.upload_chunk(session, "a", 1, raw[:10])
    with pytest.raises(ValidationError, match="incomplete"):
        service.finish_upload(session, "a")
    service.upload_chunk(session, "a", 0, raw[:10])
    service.upload_chunk(session, "a", 10, raw[10:])
    assert service.finish_upload(session, "a")["bytes"] == len(raw)
    workspace.decks[0]["revision"] = 2
    with pytest.raises(ConflictError, match="changed after"):
        service.commit(session)
    assert not list((tmp_path / "alpha" / "cards").glob("*.zip"))
    service.abort(session)


def test_invalid_chunk_zip_and_deck_revision_never_publish(tmp_path):
    service, workspace, session, filename, raw = ready_upload(tmp_path)
    with pytest.raises(ConflictError, match="changed after"):
        service.begin_upload(session, "a", filename, len(raw), 0)
    with pytest.raises(ValidationError, match="filename"):
        service.begin_upload(session, "a", "../escape.zip", len(raw), 1)
    service.begin_upload(session, "a", filename, 3, 1)
    with pytest.raises(ValidationError, match="chunk size"):
        service.upload_chunk(session, "a", 0, raw)
    service.upload_chunk(session, "a", 0, b"bad")
    with pytest.raises(ValidationError, match="valid ZIP"):
        service.finish_upload(session, "a")
    service.abort(session)
    assert not list((tmp_path / "alpha" / "cards").glob("*.zip"))


@pytest.mark.parametrize("failure", ["exception", "cancel", "collision"])
def test_commit_failure_restores_prior_zip_selection_and_releases_lock(tmp_path, failure):
    service, workspace, session, filename, raw = ready_upload(tmp_path)
    service.begin_upload(session, "a", filename, len(raw), 1)
    service.upload_chunk(session, "a", 0, raw)
    service.finish_upload(session, "a")
    cards = tmp_path / "alpha" / "cards"
    old = make_zip(cards / (filename if failure == "collision" else "approved.zip"), b"approved")
    original = old.read_bytes()
    def run(*args, **kwargs):
        raise OSError("checker failed to start")
    service.process_runner = run
    with pytest.raises(ValidationError, match="previous ZIPs are unchanged"):
        service.commit(session, cancel=lambda: failure == "cancel")
    assert old.read_bytes() == original
    assert sorted(path.name for path in cards.glob("*.zip")) == [old.name]
    workspace.decks[0]["status"] = "prepared"
    service.abort(service.start(["a"])["id"])


def test_commit_rejects_abort_and_second_commit_while_checker_runs(tmp_path):
    service, workspace, session, filename, raw = ready_upload(tmp_path)
    service.begin_upload(session, "a", filename, len(raw), 1)
    service.upload_chunk(session, "a", 0, raw)
    service.finish_upload(session, "a")
    def run(*args, **kwargs):
        with pytest.raises(ConflictError, match="in progress"):
            service.abort(session)
        with pytest.raises(ConflictError, match="in progress"):
            service.commit(session)
        return type("Result", (), {"returncode": 0, "stdout": "Changed: 2 | New: 1 | Removed: 0 | Unchanged: 10", "stderr": ""})()
    service.process_runner = run
    assert service.commit(session)["counts"] == {"changed": 2, "new": 1, "removed": 0, "unchanged": 10}


def test_construction_does_not_clean_or_scan_old_staging(tmp_path):
    app_root = tmp_path / "ProxyFoundry"
    app_root.mkdir()
    old = tmp_path / ".proxyfoundry-batch-review-old"
    old.mkdir()
    (old / "keep.zip").write_bytes(b"recoverable")
    service = DeveloperBatchReview(app_root, Workspace(tmp_path, []))
    assert (old / "keep.zip").read_bytes() == b"recoverable"
    assert not service.available()


def test_abandoned_tab_expiry_keeps_staging_and_releases_lease(tmp_path):
    service, workspace, session, filename, raw = ready_upload(tmp_path)
    service.begin_upload(session, "a", filename, len(raw), 1)
    service.upload_chunk(session, "a", 0, raw)
    old = service._sessions[session]
    old["created"] = 0
    workspace.decks[0]["status"] = "prepared"
    replacement = service.start(["a"])
    assert (old["stage"] / filename).read_bytes() == raw
    service.abort(replacement["id"])


def test_folder_alias_overrides_same_name_and_reloads_between_batches(tmp_path):
    service, _, _ = setup(tmp_path, [{"id": "a", "name": "Time Lords", "status": "prepared"}])
    for folder in ("doctor_who", "doctor_who_new"):
        (tmp_path / folder / "cards").mkdir(parents=True)
    for target in ("doctor_who", "doctor_who_new"):
        service.folder_mapping_path.write_text(json.dumps({"time_lords": target}), encoding="utf-8")
        session = service.start(["a"])["id"]
        assert service._sessions[session]["decks"][0]["cards"] == (tmp_path / target / "cards").resolve()
        service.abort(session)
    service.folder_mapping_path.write_text("{}", encoding="utf-8")
    assert service._cards_folder("Time Lords") == (tmp_path / "time lords" / "cards").resolve()
    service.folder_mapping_path.unlink()
    assert service._cards_folder("Time Lords") == (tmp_path / "time lords" / "cards").resolve()


def test_unmapped_deck_preserves_space_underscore_and_case_matching(tmp_path):
    service, _, _ = setup(tmp_path, [{"id": "a", "name": "Hulk Pack", "status": "prepared"}])
    (tmp_path / "hulk pack").rename(tmp_path / "hulk_pack")
    service.folder_mapping_path.write_text(json.dumps({"Other deck": "unused"}), encoding="utf-8")
    assert service._cards_folder("HULK PACK") == (tmp_path / "hulk_pack" / "cards").resolve()


@pytest.mark.parametrize("configured", [
    [], {"Alpha": "../outside"}, {"Alpha": "C:\\outside"}, {"Alpha": ".."},
    {"Alpha": ""}, {"Alpha": None}, {"Alpha": "nested/folder"},
    {"Alpha": " folder "}, {"Alpha": "folder."}, {"": "folder"},
    {"Alpha": "one", "ALPHA": "two"},
])
def test_invalid_folder_mapping_fails_before_creating_batch_and_releases_lock(tmp_path, configured):
    service, _, _ = setup(tmp_path, [{"id": "a", "name": "Alpha", "status": "prepared"}])
    service.folder_mapping_path.write_text(json.dumps(configured), encoding="utf-8")
    with pytest.raises(ValidationError):
        service.start(["a"])
    assert not list(tmp_path.glob(".proxyfoundry-batch-review-*"))
    service.folder_mapping_path.write_text("{}", encoding="utf-8")
    service.abort(service.start(["a"])["id"])


def test_missing_alias_target_does_not_fall_back_to_wrong_directory(tmp_path):
    service, _, _ = setup(tmp_path, [{"id": "a", "name": "Alpha", "status": "prepared"}])
    service.folder_mapping_path.write_text('{"Alpha": "missing"}', encoding="utf-8")
    with pytest.raises(ValidationError, match="Mapping points to missing/cards"):
        service.start(["a"])
    (tmp_path / "missing").mkdir()
    with pytest.raises(ValidationError, match="found 0"):
        service.start(["a"])


def test_aliases_cannot_publish_two_decks_to_one_directory(tmp_path):
    service, _, _ = setup(tmp_path, [{"id": "a", "name": "Alpha", "status": "prepared"},
                                   {"id": "b", "name": "Beta", "status": "prepared"}])
    service.folder_mapping_path.write_text('{"Beta": "alpha"}', encoding="utf-8")
    with pytest.raises(ValidationError, match="same Cards folder"):
        service.start(["a", "b"])


def test_malformed_mapping_reports_config_file(tmp_path):
    service, _, _ = setup(tmp_path, [{"id": "a", "name": "Alpha", "status": "prepared"}])
    service.folder_mapping_path.write_text('{"Alpha":', encoding="utf-8")
    with pytest.raises(ValidationError, match="Invalid JSON.*batch-review-folders.json"):
        service.start(["a"])
