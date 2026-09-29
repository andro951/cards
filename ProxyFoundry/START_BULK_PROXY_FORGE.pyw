"""Double-click preview for the static website; no console or cloud account needed."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from urllib.request import urlopen
import subprocess
import sys
import webbrowser

ROOT = Path(__file__).resolve().parent
PORT = 8767
CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
SITE_MARKER = b'<meta name="proxy-foundry" content="workspace-v1">'


class QuietSite(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def address(port=PORT):
    return f'http://127.0.0.1:{port}/'


def is_foundry_preview(port=PORT):
    try:
        with urlopen(address(port), timeout=1) as response:
            return response.status == 200 and SITE_MARKER in response.read(4096)
    except OSError:
        return False


def make_server(directory, port=PORT):
    handler = partial(QuietSite, directory=str(directory))
    server = ThreadingHTTPServer(('127.0.0.1', port), handler)
    server.daemon_threads = True
    return server


def build_and_start(events):
    if sys.version_info < (3, 10):
        events.put(('error', 'Python 3.10 or newer is required for the local preview.'))
        return

    if is_foundry_preview():
        events.put(('existing', address()))
        return

    events.put(('status', 'Building the website…'))
    try:
        build = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'build_web.py')],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
            creationflags=CREATE_NO_WINDOW, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        events.put(('error', f'The website could not be built: {error}'))
        return

    if build.returncode:
        detail = (build.stderr or build.stdout).strip()[-2500:]
        events.put(('error', f'The website build failed.\n\n{detail}'))
        return

    events.put(('status', 'Opening the local preview…'))
    try:
        server = make_server(ROOT / 'dist')
    except OSError as error:
        events.put(('error', f'Local preview port {PORT} is in use. Close the other application and try again.\n\n{error}'))
        return

    Thread(target=server.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()
    events.put(('ready', server))


def main():
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title('Bulk Proxy Forge · Local Preview')
    root.geometry('440x210')
    root.resizable(False, False)
    root.configure(bg='#15171a')
    events = Queue()
    active = {'server': None}

    heading = tk.Label(root, text='Bulk Proxy Forge', font=('Segoe UI', 17, 'bold'), fg='#f2b681', bg='#15171a')
    heading.pack(pady=(22, 5))
    status = tk.Label(root, text='Starting…', font=('Segoe UI', 10), fg='#ede6de', bg='#15171a')
    status.pack()
    detail = tk.Label(root, text='Keep this window open while using the local website.', font=('Segoe UI', 9), fg='#a9aeb7', bg='#15171a')
    detail.pack(pady=(10, 16))
    buttons = tk.Frame(root, bg='#15171a')
    buttons.pack()

    def stop():
        server = active['server']
        if server:
            server.shutdown()
            server.server_close()
        root.destroy()

    def open_site():
        webbrowser.open(address(), new=1)

    open_button = tk.Button(buttons, text='Open website', command=open_site, state='disabled', bg='#e39355', fg='#22170f', relief='flat', padx=14, pady=6)
    open_button.pack(side='left', padx=6)
    stop_button = tk.Button(buttons, text='Stop preview', command=stop, bg='#30343a', fg='#ede6de', relief='flat', padx=14, pady=6)
    stop_button.pack(side='left', padx=6)
    root.protocol('WM_DELETE_WINDOW', stop)

    def update():
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == 'status':
                    status.configure(text=value)
                elif kind == 'ready':
                    active['server'] = value
                    status.configure(text=address())
                    open_button.configure(state='normal')
                    open_site()
                elif kind == 'existing':
                    webbrowser.open(value, new=1)
                    messagebox.showinfo('Bulk Proxy Forge', 'The local website is already running. Close its preview window before restarting to load new code.')
                    root.destroy()
                    return
                elif kind == 'error':
                    messagebox.showerror('Bulk Proxy Forge', value)
                    root.destroy()
                    return
        except Empty:
            root.after(100, update)

    Thread(target=build_and_start, args=(events,), daemon=True).start()
    root.after(100, update)
    root.mainloop()


if __name__ == '__main__':
    main()
