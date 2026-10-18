"""Static local preview transport; application work stays in the browser."""
from http.server import ThreadingHTTPServer


class StaticSiteServer(ThreadingHTTPServer):
    #Module imports and image tiles arrive in bursts. The default backlog of
    #five can refuse connections while the accept thread is descheduled.
    request_queue_size=128