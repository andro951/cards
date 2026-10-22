"""Static local preview transport; application work stays in the browser."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler


class StaticSiteServer(ThreadingHTTPServer):
    #Module imports and image tiles arrive in bursts. The default backlog of
    #five can refuse connections while the accept thread is descheduled.
    request_queue_size=128


class BatchPreviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        bridge = getattr(self.server, "batch_review_bridge", None)
        if bridge and bridge.handle(self):
            return
        super().do_GET()

    def do_POST(self):
        bridge = getattr(self.server, "batch_review_bridge", None)
        if not bridge or not bridge.handle(self):
            self.send_error(404)