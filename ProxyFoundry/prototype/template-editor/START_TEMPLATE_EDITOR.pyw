"""Open the separate editor; keep its local host off the user's desktop."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
ORIGIN = 'http://127.0.0.1:8778/'


def running():
    try:
        with urllib.request.urlopen(ORIGIN + 'default-template.json', timeout=1) as response:
            return json.load(response).get('format') == 'bulk-proxy-forge-visual-template'
    except (OSError, ValueError):
        return False


if not running():
    interpreter = ROOT.parents[1] / '.venv/Scripts/python.exe'
    if not interpreter.exists():
        interpreter = Path(sys.executable)
    log = open(Path(tempfile.gettempdir()) / 'BulkProxyForge-TemplateEditor.log', 'a', encoding='utf-8')
    subprocess.Popen([str(interpreter), str(ROOT / 'server.py')], cwd=ROOT, stdout=log, stderr=log,
                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    for _ in range(30):
        if running():
            break
        time.sleep(0.1)

if running():
    webbrowser.open(ORIGIN)