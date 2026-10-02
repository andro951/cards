"""A paused accept loop must accommodate browser module/image bursts."""
import http.server
import socket

from scripts.static_server import StaticSiteServer


def test_local_preview_accepts_pending_browser_connection_burst():
    server=StaticSiteServer(('127.0.0.1',0),http.server.SimpleHTTPRequestHandler)
    sockets=[]
    try:
        #No accept thread yet: a busy/descheduled preview must retain the burst
        #rather than refuse a module connection and abort the whole import.
        for _ in range(32):sockets.append(socket.create_connection(server.server_address,timeout=1))
        assert len(sockets)==32
    finally:
        for connection in sockets:connection.close()
        server.server_close()