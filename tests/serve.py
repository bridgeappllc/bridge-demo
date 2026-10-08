"""Static server for tests: serves /workspace/bridge-real, injecting the local
Supabase-compatible stack's URL + anon key into the config block of index.html."""
import http.server, os, sys, functools
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = os.environ.get("SB_URL", "http://127.0.0.1:54321"); KEY = os.environ["SB_KEY"]
class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        p = self.path.split("?")[0].split("#")[0]
        if p in ("/", "/index.html"):
            html = open(os.path.join(ROOT, "index.html"), encoding="utf8").read()
            html = html.replace('SUPABASE_URL: ""', f'SUPABASE_URL: "{URL}"', 1).replace('SUPABASE_ANON_KEY: ""', f'SUPABASE_ANON_KEY: "{KEY}"', 1)
            b = html.encode(); self.send_response(200); self.send_header("content-type", "text/html; charset=utf-8"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else: super().do_GET()
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8080), functools.partial(H, directory=ROOT)).serve_forever()
