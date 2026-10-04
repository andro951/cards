"""Separate template editor host. No production workspace or generation jobs."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit, quote
from urllib.request import urlopen
import argparse
import hashlib
import mimetypes
import threading
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
UPSTREAM = 'https://raw.githubusercontent.com/Investigamer/cardconjurer/2fcddba8966156d484cedf54d8214996748dd5e1'
COMPAT = 'https://raw.githubusercontent.com/d1rtyskittl3z/Card-Cipherist/47087b3fc21e2cef61c58b9ebf180968ee991658/public'
CACHE = Path(tempfile.gettempdir()) / 'BulkProxyForge-TemplateEditor-assets'
LOCK = threading.Lock()


def shell():
    document = ET.Element('html', lang='en')
    head = ET.SubElement(document, 'head')
    ET.SubElement(head, 'meta', charset='utf-8')
    ET.SubElement(head, 'meta', name='viewport', content='width=device-width, initial-scale=1')
    ET.SubElement(head, 'title').text = 'BulkProxyForge Template Editor Prototype'
    body = ET.SubElement(document, 'body')
    ET.SubElement(body, 'script', type='module', src='/editor.js').text = ''
    return b'<!doctype html>' + ET.tostring(document, encoding='utf-8', method='html')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if '\\' in path or '\x00' in path or any(p in {'.', '..'} for p in path.split('/')):
            self.send_error(400)
            return
        try:
            if path == '/':
                raw, mime = shell(), 'text/html'
            elif path.startswith(('/img/', '/fonts/')):
                if Path(path).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.svg', '.webp', '.ttf', '.otf', '.woff', '.woff2'}:
                    self.send_error(400)
                    return
                CACHE.mkdir(exist_ok=True)
                destination = CACHE / hashlib.sha256(path.encode()).hexdigest()
                with LOCK:
                    cached = destination.read_bytes() if destination.exists() else None
                if cached is None:
                    from urllib.error import HTTPError
                    try:
                        with urlopen(UPSTREAM + quote(path, safe='/'), timeout=20) as response:
                            cached = response.read(24 * 1024 * 1024 + 1)
                    except HTTPError as error:
                        if error.code != 404:
                            raise
                        with urlopen(COMPAT + quote(path, safe='/'), timeout=20) as response:
                            cached = response.read(24 * 1024 * 1024 + 1)
                    if len(cached) > 24 * 1024 * 1024:
                        self.send_error(413)
                        return
                    with LOCK:
                        destination.write_bytes(cached)
                raw, mime = cached, mimetypes.guess_type(path)[0] or 'application/octet-stream'
            else:
                target = (ROOT / path.lstrip('/')).resolve()
                if not target.is_relative_to(ROOT) or not target.is_file() or target.suffix not in {'.js', '.json'}:
                    self.send_error(404)
                    return
                raw, mime = target.read_bytes(), 'application/javascript' if target.suffix == '.js' else 'application/json'
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'public, max-age=31536000, immutable' if path.startswith(('/img/', '/fonts/')) else 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; img-src 'self' data: blob:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)
        except (OSError, ValueError) as error:
            self.send_error(502, 'Asset unavailable: ' + str(error)[:180])


def create_server(port=8778):
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8778)
    args = parser.parse_args()
    server = create_server(args.port)
    print(f'Template editor: http://127.0.0.1:{server.server_port}/', flush=True)
    server.serve_forever()