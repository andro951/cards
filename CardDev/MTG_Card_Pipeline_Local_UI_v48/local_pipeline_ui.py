#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
PIPELINE = ROOT / "pipeline" / "scryfall_deck_to_cardconjurer.py"
IMAGE_DOWNLOADER = ROOT / "tools" / "download_scryfall_deck_images_zip.py"
TOKEN_MAKER = ROOT / "tools" / "make_copy_tokens.py"
OUTPUTS_ROOT = ROOT / "outputs"
OUTPUTS_ROOT.mkdir(exist_ok=True)


def default_scryfall_cache_dir() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "MTG_Card_Pipeline_Local_UI" / "scryfall_cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "MTG_Card_Pipeline_Local_UI" / "scryfall_cache"
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "MTG_Card_Pipeline_Local_UI" / "scryfall_cache"


SCRYFALL_CACHE_DIR = default_scryfall_cache_dir()
SCRYFALL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

STATE_LOCK = threading.Lock()
STATE: dict[str, Any] = {
    "running": False,
    "status": "idle",
    "job_type": None,
    "exit_code": None,
    "logs": [],
    "command": [],
    "outputs": [],
    "output_dir": None,
    "started_at": None,
    "finished_at": None,
    "process": None,
}


def resolve_project(raw: str) -> Path:
    raw = os.path.expandvars(os.path.expanduser(raw.strip()))
    if not raw:
        raise ValueError("Project folder is required.")
    p = Path(raw)
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def safe_slug(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    return text.strip("._-") or "project"


def validate_deck_url(deck_url: str) -> None:
    parsed = urllib.parse.urlparse(deck_url)
    if parsed.netloc.lower() not in {"scryfall.com", "www.scryfall.com"} or "/decks/" not in parsed.path:
        raise ValueError("Deck link must be a Scryfall deck URL containing /decks/<uuid>.")


def discover_projects() -> list[str]:
    found: list[str] = []
    bases = [ROOT, ROOT.parent]
    seen: set[Path] = set()
    for base in bases:
        try:
            children = list(base.iterdir())
        except OSError:
            continue
        for child in children:
            try:
                rp = child.resolve()
                if rp in seen or not child.is_dir():
                    continue
                seen.add(rp)
                if (child / "art").is_dir() and (child / "set_symbol").is_dir():
                    found.append(str(rp))
            except OSError:
                continue
    return sorted(set(found), key=str.lower)


def open_in_file_manager(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def append_log(line: str) -> None:
    with STATE_LOCK:
        STATE["logs"].append(line)


def set_failed(exc: Exception) -> None:
    append_log(f"ERROR: {exc}\n")
    with STATE_LOCK:
        STATE.update({
            "running": False,
            "status": "error",
            "exit_code": -1,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "process": None,
        })


def run_subprocess_job(job_type: str, cmd: list[str], run_dir: Path, output_resolver: Callable[[], list[Path]]) -> None:
    with STATE_LOCK:
        STATE.update({
            "running": True,
            "status": "running",
            "job_type": job_type,
            "exit_code": None,
            "logs": [],
            "command": cmd,
            "outputs": [],
            "output_dir": str(run_dir),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        })

    append_log("$ " + subprocess.list2cmdline(cmd) + "\n\n")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        with STATE_LOCK:
            STATE["process"] = proc

        assert proc.stdout is not None
        for line in proc.stdout:
            append_log(line)
        exit_code = proc.wait()

        outputs = []
        for p in output_resolver():
            if p.is_file():
                outputs.append({"name": p.name, "path": str(p.resolve()), "size": p.stat().st_size})

        with STATE_LOCK:
            STATE.update({
                "running": False,
                "status": "success" if exit_code == 0 else "error",
                "exit_code": exit_code,
                "outputs": outputs,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "process": None,
            })
        if exit_code == 0:
            append_log("\n=== SUCCESS ===\n")
        else:
            append_log(f"\n=== ERROR: process exited with code {exit_code} ===\n")
    except Exception as exc:
        set_failed(exc)


def run_pipeline(payload: dict[str, Any]) -> None:
    try:
        deck_url = str(payload.get("deck_url", "")).strip()
        validate_deck_url(deck_url)
        project = resolve_project(str(payload.get("project", "")))
        include_outside = bool(payload.get("include_outside", False))
        repo = str(payload.get("repo", "andro951/cards")).strip() or "andro951/cards"
        branch = str(payload.get("branch", "main")).strip() or "main"
        repo_project_path = str(payload.get("repo_project_path", "")).strip() or project.name
        use_scryfall_art = bool(payload.get("use_scryfall_art", False))
        refresh_card_data = bool(payload.get("refresh_card_data", False))
        allow_missing_art = bool(payload.get("allow_missing_art", False))
        allow_missing_symbols = bool(payload.get("allow_missing_symbols", False))
        no_auto_fit = bool(payload.get("no_auto_fit", False))
        request_delay = str(payload.get("request_delay", "0.125")).strip() or "0.125"

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = OUTPUTS_ROOT / f"{stamp}_{safe_slug(project.name)}"
        run_dir.mkdir(parents=True, exist_ok=False)
        data_out = run_dir / f"generated_{safe_slug(project.name)}_card_data.json"
        cc_out = run_dir / f"generated_{safe_slug(project.name)}_cards.cardconjurer"
        manifest_out = run_dir / f"generated_{safe_slug(project.name)}_manifest.json"

        cmd = [
            sys.executable, str(PIPELINE), deck_url,
            "--project", str(project),
            "--repo", repo,
            "--branch", branch,
            "--repo-project-path", repo_project_path,
            "--request-delay", request_delay,
            "--output-data", str(data_out),
            "--output-cardconjurer", str(cc_out),
            "--manifest", str(manifest_out),
            "--scryfall-cache-dir", str(SCRYFALL_CACHE_DIR),
        ]
        if refresh_card_data:
            cmd.append("--refresh-card-data")
        if include_outside:
            cmd.append("--include-outside-the-game")
        if use_scryfall_art:
            cmd.append("--use-scryfall-art")
        if allow_missing_art:
            cmd.append("--allow-missing-art")
        if allow_missing_symbols:
            cmd.append("--allow-missing-symbols")
        if no_auto_fit:
            cmd.append("--no-auto-fit")

        run_subprocess_job("pipeline", cmd, run_dir, lambda: [cc_out, data_out, manifest_out])
    except Exception as exc:
        set_failed(exc)


def run_image_download(payload: dict[str, Any]) -> None:
    try:
        deck_url = str(payload.get("deck_url", "")).strip()
        validate_deck_url(deck_url)
        include_outside = bool(payload.get("include_outside", False))
        request_delay = str(payload.get("request_delay", "0.12")).strip() or "0.12"

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = OUTPUTS_ROOT / f"{stamp}_deck_images"
        image_dir = run_dir / "images"
        run_dir.mkdir(parents=True, exist_ok=False)

        cmd = [
            sys.executable, str(IMAGE_DOWNLOADER), deck_url,
            "--out", str(image_dir),
            "--delay", request_delay,
        ]
        if include_outside:
            cmd.append("--include-outside-the-game")

        def outputs() -> list[Path]:
            zips = sorted(run_dir.glob("*.zip"))
            manifest = image_dir / "manifest.json"
            return zips + [manifest]

        run_subprocess_job("images", cmd, run_dir, outputs)
    except Exception as exc:
        set_failed(exc)


def resolve_local_file(raw: str, suffix: str | None = None) -> Path:
    raw = os.path.expandvars(os.path.expanduser(str(raw or "").strip()))
    if not raw:
        raise ValueError("Input file is required.")
    p = Path(raw)
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve()
    if not p.is_file():
        raise ValueError(f"Input file does not exist: {p}")
    if suffix and p.suffix.lower() != suffix.lower():
        raise ValueError(f"Expected a {suffix} file: {p}")
    return p


def run_token_generation(payload: dict[str, Any]) -> None:
    try:
        input_file = resolve_local_file(str(payload.get("input_file", "")), ".cardconjurer")
        raw_specs = payload.get("tokens")
        if not isinstance(raw_specs, list) or not raw_specs:
            raise ValueError("Add at least one token row.")

        specs: list[dict[str, Any]] = []
        for i, raw in enumerate(raw_specs, start=1):
            if not isinstance(raw, dict):
                raise ValueError(f"Token row {i} is invalid.")
            source_name = str(raw.get("source_name", "")).strip()
            if not source_name:
                raise ValueError(f"Token row {i}: Source card is required.")
            spec: dict[str, Any] = {
                "source_name": source_name,
                "token_key_suffix": " — Token",
            }
            if bool(raw.get("nonlegendary", False)):
                spec["nonlegendary"] = True
            type_override = str(raw.get("type_override", "")).strip()
            if type_override:
                # The helper interprets this as a creature-subtype replacement,
                # e.g. Human Warlock -> Illusion while keeping Legendary Creature.
                spec["replace_creature_subtypes"] = type_override
            pt_override = str(raw.get("pt_override", "")).strip()
            if pt_override:
                if not re.fullmatch(r"[^/\s]+\s*/\s*[^/\s]+", pt_override):
                    raise ValueError(f"Token row {i}: P/T override should look like 0/1, 3/3, */*, etc.")
                spec["power_toughness"] = re.sub(r"\s+", "", pt_override)
            specs.append(spec)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = OUTPUTS_ROOT / f"{stamp}_tokens"
        run_dir.mkdir(parents=True, exist_ok=False)
        spec_path = run_dir / "token_specs.json"
        spec_path.write_text(json.dumps(specs, indent=2, ensure_ascii=False), encoding="utf-8")
        output_file = run_dir / f"{safe_slug(input_file.stem)}_with_tokens.cardconjurer"

        cmd = [
            sys.executable,
            str(TOKEN_MAKER),
            str(input_file),
            str(output_file),
            "--spec", str(spec_path),
        ]
        run_subprocess_job("tokens", cmd, run_dir, lambda: [output_file, spec_path])
    except Exception as exc:
        set_failed(exc)


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MTG Card Tools</title>
<style>
:root{color-scheme:dark;--bg:#111318;--panel:#1a1e26;--field:#0d1015;--border:#343b49;--text:#eef1f6;--muted:#9ba6b6;--ok:#6ee7a0;--err:#ff7b86;--run:#7ca8ff;--accent:#2858a8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,Segoe UI,Arial,sans-serif}
main{max-width:1050px;margin:28px auto;padding:0 18px 40px}.panel{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:18px;margin-bottom:16px}
h1{font-size:24px;margin:0 0 5px}.sub{color:var(--muted);margin-bottom:18px}.tabs{display:flex;gap:8px;margin:18px 0 16px}.tabbtn{background:#202530}.tabbtn.active{background:var(--accent);border-color:#477bd0}.tab{display:none}.tab.active{display:block}
.grid{display:grid;grid-template-columns:1fr 180px;gap:12px}.full{grid-column:1/-1}label{display:block;font-weight:650;margin-bottom:6px}input[type=text],input[type=number]{width:100%;background:var(--field);border:1px solid var(--border);border-radius:8px;color:var(--text);padding:10px 11px;font:inherit}
.row{display:flex;gap:9px;align-items:center}.row input[type=text]{flex:1}.check{display:flex;gap:8px;align-items:center;margin:10px 0}.check label{margin:0;font-weight:500}
button,.buttonlike{border:1px solid var(--border);border-radius:8px;background:#252b36;color:var(--text);padding:9px 13px;font:inherit;font-weight:650;cursor:pointer;text-decoration:none;display:inline-block}button:hover,.buttonlike:hover{filter:brightness(1.12)}button.primary{background:var(--accent);border-color:#477bd0}button.danger{background:#6f2830;border-color:#9a414c}button:disabled{opacity:.5;cursor:not-allowed}
details{margin-top:10px}summary{cursor:pointer;color:#cbd5e1;font-weight:650}.advanced{margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:12px}.actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}
.status{display:flex;gap:9px;align-items:center;font-weight:700}.dot{width:10px;height:10px;border-radius:50%;background:#7c8798}.running .dot{background:var(--run)}.success .dot{background:var(--ok)}.error .dot{background:var(--err)}
pre{background:#090b0f;border:1px solid var(--border);border-radius:8px;padding:13px;min-height:310px;max-height:560px;overflow:auto;white-space:pre-wrap;word-break:break-word;font:13px/1.5 Consolas,monospace;color:#dce4ef}#command{min-height:0;max-height:130px;color:#aebbd0}.outputs{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.small{font-size:13px;color:var(--muted)}.note{padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:#131821;color:#c7d1df;margin:12px 0}.tokenrow{border:1px solid var(--border);border-radius:10px;padding:12px;margin:10px 0;background:#151922}.tokenrowgrid{display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:10px;align-items:end}.tokenrow .check{margin:0 0 4px}.tokenrow button{padding:8px 11px}code{font-family:Consolas,monospace;color:#dce4ef}
@media(max-width:700px){.grid,.advanced,.tokenrowgrid{grid-template-columns:1fr}.full{grid-column:auto}.tabs{flex-direction:column}}
</style>
</head>
<body><main>
<div class="panel">
<h1>MTG Card Tools</h1>
<div class="sub">Card Conjurer pipeline and exact Scryfall deck-image downloader.</div>
<div class="tabs"><button class="tabbtn active" data-tab="pipelineTab">Card Pipeline</button><button class="tabbtn" data-tab="imagesTab">Download Deck Images</button></div>

<div id="pipelineTab" class="tab active">
  <div class="grid">
    <div class="full"><label for="deck">Scryfall deck link</label><input id="deck" type="text" placeholder="https://scryfall.com/@user/decks/..."></div>
    <div class="full"><label for="project">Local project folder</label><div class="row"><input id="project" type="text" list="projectSuggestions" placeholder="C:\...\cards\hulk_pack or hulk_pack"><button id="browse">Browse…</button></div><datalist id="projectSuggestions"></datalist></div>
  </div>
  <div class="check"><input id="outside" type="checkbox"><label for="outside">Include Outside The Game cards</label></div>
  <details><summary>Advanced options</summary><div class="advanced">
    <div><label for="repo">GitHub repo</label><input id="repo" type="text" value="andro951/cards"></div>
    <div><label for="branch">Branch</label><input id="branch" type="text" value="main"></div>
    <div><label for="repoPath">Project path inside repo</label><input id="repoPath" type="text" placeholder="Auto: project folder name"></div>
    <div><label for="delay">Scryfall request delay (seconds)</label><input id="delay" type="number" min="0.11" step="0.005" value="0.125"></div>
    <div class="check"><input id="useScryfallArt" type="checkbox"><label for="useScryfallArt">Use Scryfall art as fallback (always prefer custom GitHub art first)</label></div>
    <div class="check"><input id="refreshCardData" type="checkbox"><label for="refreshCardData">Fetch new card data (only refreshes cache entries 7+ days old)</label></div>
    <div class="check"><input id="missingArt" type="checkbox"><label for="missingArt">Allow missing local art</label></div>
    <div class="check"><input id="missingSymbols" type="checkbox"><label for="missingSymbols">Allow missing set symbols</label></div>
    <div class="check"><input id="noFit" type="checkbox"><label for="noFit">Disable auto-fit</label></div>
  </div></details>
  <div class="actions"><button class="primary" id="runPipeline">Run Pipeline</button></div>
  <div style="border-top:1px solid var(--border);margin:22px 0 16px"></div>
  <h2 style="font-size:19px;margin:0 0 8px">Copy Token Maker</h2>
  <div class="small" style="margin-bottom:12px">Create M15 bordered token-frame copies from an existing Card Conjurer batch.</div>
  <div class="grid">
    <div class="full"><label for="tokenInput">Existing .cardconjurer file</label><div class="row"><input id="tokenInput" type="text" placeholder="C:\...\generated_deck_cards.cardconjurer"><button id="browseTokenInput">Browse…</button></div></div>
  </div>
  <div class="note"><b>Type override</b> replaces the copied creature's subtype(s) only. Example: <code>Legendary Creature - Human Warlock</code> with override <code>Illusion</code> becomes <code>Legendary Creature - Illusion</code>. Check <b>Non-legendary</b> separately when an effect removes Legendary. Leave an override blank to keep the original value.</div>
  <div id="tokenRows"></div>
  <div class="actions"><button id="addTokenRow">+ Add Token</button><button class="primary" id="runTokens">Generate Tokens</button></div>
</div>

<div id="imagesTab" class="tab">
  <div class="grid"><div class="full"><label for="imageDeck">Scryfall deck link</label><input id="imageDeck" type="text" placeholder="https://scryfall.com/@user/decks/..."></div></div>
  <div class="check"><input id="imageOutside" type="checkbox"><label for="imageOutside">Include Outside The Game cards</label></div>
  <div class="note">Downloads the exact printing's full-card PNG directly from the image URLs embedded in the deck export. It does <b>not</b> make a per-card API request just to discover image URLs.</div>
  <details><summary>Advanced options</summary><div class="advanced"><div><label for="imageDelay">Image request delay (seconds)</label><input id="imageDelay" type="number" min="0" step="0.01" value="0.12"></div></div></details>
  <div class="actions"><button class="primary" id="runImages">Download &amp; ZIP Images</button></div>
</div>

</div>

<div class="panel">
<div id="status" class="status idle"><span class="dot"></span><span id="statusText">Idle</span></div>
<div class="small" id="timing"></div>
<label style="margin-top:12px">Command</label><pre id="command">—</pre>
</div>

<div class="panel">
<div class="row" style="justify-content:space-between;flex-wrap:wrap"><label style="margin:0">Logs / errors</label><div class="actions" style="margin:0"><button id="copy">Copy Logs</button><button id="clear">Clear View</button><button id="openOutput" disabled>Open Output Folder</button><button class="danger" id="stop" disabled>Stop</button></div></div>
<pre id="logs"></pre><div id="outputs" class="outputs"></div>
</div>
</main>
<script>
const $=id=>document.getElementById(id);let logText='';let polling=null;
function pipelinePayload(){return {deck_url:$('deck').value.trim(),project:$('project').value.trim(),include_outside:$('outside').checked,repo:$('repo').value.trim(),branch:$('branch').value.trim(),repo_project_path:$('repoPath').value.trim(),request_delay:$('delay').value,use_scryfall_art:$('useScryfallArt').checked,refresh_card_data:$('refreshCardData').checked,allow_missing_art:$('missingArt').checked,allow_missing_symbols:$('missingSymbols').checked,no_auto_fit:$('noFit').checked}}
function imagePayload(){return {deck_url:$('imageDeck').value.trim(),include_outside:$('imageOutside').checked,request_delay:$('imageDelay').value}}
let tokenRowSeq=0;
function addTokenRow(values={}){const id=++tokenRowSeq;const row=document.createElement('div');row.className='tokenrow';row.dataset.id=id;row.innerHTML=`<div class="tokenrowgrid"><div><label>Source card</label><input class="tokenSource" type="text" placeholder="Cloud, Midgar Mercenary" value="${(values.source_name||'').replaceAll('&','&amp;').replaceAll('"','&quot;')}"></div><div><label>Type override</label><input class="tokenType" type="text" placeholder="e.g. Illusion" value="${(values.type_override||'').replaceAll('&','&amp;').replaceAll('"','&quot;')}"></div><div><label>P/T override</label><input class="tokenPT" type="text" placeholder="e.g. 0/1" value="${(values.pt_override||'').replaceAll('&','&amp;').replaceAll('"','&quot;')}"></div><div><div class="check"><input class="tokenNonlegendary" id="tokenNonlegendary${id}" type="checkbox" ${values.nonlegendary?'checked':''}><label for="tokenNonlegendary${id}">Non-legendary</label></div><button class="removeTokenRow" type="button">Remove</button></div></div>`;row.querySelector('.removeTokenRow').onclick=()=>row.remove();$('tokenRows').appendChild(row)}
function tokenPayload(){return {input_file:$('tokenInput').value.trim(),tokens:[...document.querySelectorAll('.tokenrow')].map(row=>({source_name:row.querySelector('.tokenSource').value.trim(),nonlegendary:row.querySelector('.tokenNonlegendary').checked,type_override:row.querySelector('.tokenType').value.trim(),pt_override:row.querySelector('.tokenPT').value.trim()}))}}
function setStatus(s,code=null){$('status').className='status '+s;const labels={idle:'Idle',running:'Running…',success:'Success',error:'Error'};$('statusText').textContent=labels[s]||s;if(code!==null&&s!=='running')$('statusText').textContent+=` (exit ${code})`;const running=s==='running';$('runPipeline').disabled=running;$('runImages').disabled=running;$('runTokens').disabled=running;$('stop').disabled=!running}
async function refresh(){try{const r=await fetch('/api/status');const d=await r.json();logText=d.logs||'';$('logs').textContent=logText;$('logs').scrollTop=$('logs').scrollHeight;$('command').textContent=(d.command||[]).join(' ')||'—';setStatus(d.status,d.exit_code);$('timing').textContent=[d.job_type?`Job: ${d.job_type}`:'',d.started_at?`Started: ${d.started_at}`:'',d.finished_at?`Finished: ${d.finished_at}`:''].filter(Boolean).join('   ');$('outputs').innerHTML=(d.outputs||[]).map((o,i)=>`<a class="buttonlike" href="/api/download?i=${i}">${o.name}</a>`).join('');$('openOutput').disabled=!d.output_dir;if(!d.running&&polling){clearInterval(polling);polling=null}}catch(e){}}
async function start(endpoint,payload){logText='';$('logs').textContent='';$('outputs').innerHTML='';const r=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok){alert(d.error||'Could not start.');return}setStatus('running');await refresh();if(!polling)polling=setInterval(refresh,500)}
$('runPipeline').onclick=()=>{if(!$('deck').value.trim()||!$('project').value.trim()){alert('Enter both a Scryfall deck link and a local project folder.');return}start('/api/run-pipeline',pipelinePayload())};
$('runImages').onclick=()=>{if(!$('imageDeck').value.trim()){alert('Enter a Scryfall deck link.');return}start('/api/run-images',imagePayload())};
$('addTokenRow').onclick=()=>addTokenRow();
$('runTokens').onclick=()=>{if(!$('tokenInput').value.trim()){alert('Choose an existing .cardconjurer file.');return}const p=tokenPayload();if(!p.tokens.length){alert('Add at least one token row.');return}if(p.tokens.some(t=>!t.source_name)){alert('Every token row needs a Source card name.');return}start('/api/run-tokens',p)};
$('stop').onclick=async()=>{await fetch('/api/stop',{method:'POST'});setTimeout(refresh,150)};
$('copy').onclick=async()=>{try{await navigator.clipboard.writeText(logText);$('copy').textContent='Copied';setTimeout(()=>$('copy').textContent='Copy Logs',1100)}catch(e){alert('Clipboard permission was denied. Select the log text and copy it manually.')}};
$('clear').onclick=()=>{$('logs').textContent=''};
$('openOutput').onclick=async()=>{const r=await fetch('/api/open-output',{method:'POST'});const d=await r.json();if(!r.ok)alert(d.error||'Could not open output folder.')};
$('browse').onclick=async()=>{$('browse').disabled=true;try{const r=await fetch('/api/browse-project',{method:'POST'});const d=await r.json();if(d.path)$('project').value=d.path;else if(d.error)alert(d.error)}finally{$('browse').disabled=false}};
$('browseTokenInput').onclick=async()=>{$('browseTokenInput').disabled=true;try{const r=await fetch('/api/browse-cardconjurer',{method:'POST'});const d=await r.json();if(d.path)$('tokenInput').value=d.path;else if(d.error)alert(d.error)}finally{$('browseTokenInput').disabled=false}};
document.querySelectorAll('.tabbtn').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabbtn').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.id===b.dataset.tab));});
addTokenRow();
(async()=>{try{const r=await fetch('/api/projects');const d=await r.json();$('projectSuggestions').innerHTML=(d.projects||[]).map(x=>`<option value="${x.replaceAll('&','&amp;').replaceAll('"','&quot;')}"></option>`).join('');if((d.projects||[]).length===1)$('project').value=d.projects[0]}catch(e){}await refresh()})();
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    server_version = "MTGCardToolsUI/2.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def send_bytes(self, body: bytes, content_type: str, status: int = 200, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data: Any, status: int = 200) -> None:
        self.send_bytes(json.dumps(data).encode("utf-8"), "application/json; charset=utf-8", status)

    def read_json(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.send_bytes(HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/status":
            with STATE_LOCK:
                response = {k: v for k, v in STATE.items() if k != "process"}
                response["logs"] = "".join(STATE["logs"])
            self.send_json(response)
            return
        if parsed.path == "/api/projects":
            self.send_json({"projects": discover_projects()})
            return
        if parsed.path == "/api/download":
            qs = urllib.parse.parse_qs(parsed.query)
            try:
                i = int(qs.get("i", ["-1"])[0])
                with STATE_LOCK:
                    item = STATE["outputs"][i]
                p = Path(item["path"]).resolve()
                if OUTPUTS_ROOT.resolve() not in p.parents or not p.is_file():
                    raise ValueError("Invalid output path")
                self.send_bytes(p.read_bytes(), "application/octet-stream", extra={"Content-Disposition": f'attachment; filename="{p.name}"'})
            except Exception as exc:
                self.send_json({"error": str(exc)}, 404)
            return
        self.send_json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/api/run-pipeline", "/api/run-images", "/api/run-tokens"}:
            with STATE_LOCK:
                if STATE["running"]:
                    self.send_json({"error": "Another job is already in progress."}, 409)
                    return
            try:
                payload = self.read_json()
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
                return
            target = run_pipeline if parsed.path == "/api/run-pipeline" else (run_image_download if parsed.path == "/api/run-images" else run_token_generation)
            threading.Thread(target=target, args=(payload,), daemon=True).start()
            self.send_json({"ok": True}, 202)
            return
        if parsed.path == "/api/stop":
            with STATE_LOCK:
                proc = STATE.get("process")
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    append_log("\n=== STOP REQUESTED ===\n")
                    self.send_json({"ok": True})
                except Exception as exc:
                    self.send_json({"error": str(exc)}, 500)
            else:
                self.send_json({"ok": True})
            return
        if parsed.path == "/api/open-output":
            with STATE_LOCK:
                raw = STATE.get("output_dir")
            try:
                if not raw:
                    raise ValueError("No output folder exists yet.")
                open_in_file_manager(Path(raw).resolve())
                self.send_json({"ok": True})
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        if parsed.path == "/api/browse-project":
            code = (
                "import tkinter as tk; from tkinter import filedialog; "
                "r=tk.Tk(); r.withdraw(); r.attributes('-topmost', True); "
                "p=filedialog.askdirectory(title='Choose MTG project folder'); print(p); r.destroy()"
            )
            try:
                cp = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
                if cp.returncode != 0:
                    raise RuntimeError(cp.stderr.strip() or "Folder picker failed. Type the path manually instead.")
                self.send_json({"path": cp.stdout.strip()})
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        if parsed.path == "/api/browse-cardconjurer":
            code = (
                "import tkinter as tk; from tkinter import filedialog; "
                "r=tk.Tk(); r.withdraw(); r.attributes('-topmost', True); "
                "p=filedialog.askopenfilename(title='Choose Card Conjurer file', filetypes=[('Card Conjurer','*.cardconjurer'),('All files','*.*')]); print(p); r.destroy()"
            )
            try:
                cp = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
                if cp.returncode != 0:
                    raise RuntimeError(cp.stderr.strip() or "File picker failed. Type the path manually instead.")
                self.send_json({"path": cp.stdout.strip()})
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        self.send_json({"error": "Not found"}, 404)


def choose_port(start: int = 8765) -> int:
    for port in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("Could not find an available local port.")


def main() -> int:
    missing = [str(p) for p in (PIPELINE, IMAGE_DOWNLOADER, TOKEN_MAKER) if not p.is_file()]
    if missing:
        print("ERROR: required script(s) not found:\n  " + "\n  ".join(missing))
        return 2
    port = choose_port()
    url = f"http://127.0.0.1:{port}/"
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("MTG Card Tools Local UI")
    print(f"Open: {url}")
    print("Press Ctrl+C in this window to stop the local server.")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
