"""Serve the revenue workspace as static files.

The visible site is public/index.html plus the files in public/revenue-design.
This process does not compile React. Paths without a file fall back to the shell
so /leads and the other workspace routes still open.
"""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1] / "public"


class WorkspaceHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        request_path = unquote(urlsplit(self.path).path)
        relative = request_path.lstrip("/")
        candidate = (ROOT / relative).resolve()
        root = ROOT.resolve()
        if root != candidate and root not in candidate.parents:
            self.send_error(404)
            return
        if request_path != "/" and not candidate.is_file():
            if Path(relative).suffix:
                self.send_error(404)
                return
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), partial(WorkspaceHandler, directory=str(ROOT)))
    print(f"Sales Engine workspace at http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
