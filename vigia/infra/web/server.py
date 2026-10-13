"""Servidor HTTP local (stdlib): arquivos da interface, API JSON e fluxo SSE do estado."""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .api import Api, is_local_host, is_loopback, may_command

log = logging.getLogger(__name__)

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STREAM_INTERVAL = 0.5
MAX_BODY = 16 * 1024
TYPES = {".otf": "font/otf", ".ttf": "font/ttf", ".js": "text/javascript", ".css": "text/css",
         ".svg": "image/svg+xml", ".html": "text/html"}


class VigiaServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, api: Api, token: str, lan: bool):
        super().__init__(address, Handler)
        self.api, self.token, self.lan = api, token, lan

    @property
    def port(self) -> int:
        return self.server_address[1]


class Handler(BaseHTTPRequestHandler):
    server: VigiaServer
    server_version = "Vigia"

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)

    # --- acesso ---------------------------------------------------------------
    @property
    def _client(self) -> str:
        return self.client_address[0]

    def _host_ok(self) -> bool:
        return self.server.lan or is_local_host(self.headers.get("Host"), self.server.port)

    def _read_only(self) -> bool:
        return not (is_loopback(self._client) and is_local_host(self.headers.get("Host"), self.server.port))

    # --- respostas ------------------------------------------------------------
    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        if not self._host_ok():
            return self._json(421, {"erro": "host"})
        path = urlsplit(self.path).path
        if path == "/api/estado":
            return self._json(200, self.server.api.state(self._read_only()))
        if path == "/api/fluxo":
            return self._stream()
        if path in ("/", "/index.html"):
            return self._index()
        return self._static(path)

    do_HEAD = do_GET

    def do_POST(self):
        path = urlsplit(self.path).path
        if not may_command(self._client, self.headers.get("Host"), self.headers.get("X-Vigia-Token"),
                           self.server.token, self.server.port):
            return self._json(403, {"erro": "somente_leitura"})
        if self.headers.get_content_type() != "application/json":  # força preflight CORS em pedidos de outra origem
            return self._json(415, {"erro": "tipo"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json(413, {"erro": "grande"})
        resp = self.server.api.post(path, self.rfile.read(length))
        self._send(resp.status, resp.body(), "application/json; charset=utf-8")

    def _index(self):
        with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as fh:
            html = fh.read().replace("{{TOKEN}}", self.server.token if not self._read_only() else "")
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _static(self, path: str):
        full = os.path.realpath(os.path.join(STATIC, path.lstrip("/")))
        if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
            return self._json(404, {"erro": "nao_encontrado"})
        ext = os.path.splitext(full)[1].lower()
        ctype = TYPES.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            self._send(200, fh.read(), ctype)

    def _stream(self):
        """Server-Sent Events: o estado completo a cada 0,5 s enquanto a aba estiver aberta."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        read_only = self._read_only()
        try:
            while True:
                data = json.dumps(self.server.api.state(read_only), ensure_ascii=False, separators=(",", ":"))
                self.wfile.write(b"data: " + data.encode("utf-8") + b"\n\n")
                self.wfile.flush()
                time.sleep(STREAM_INTERVAL)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return


def start_server(api: Api, token: str, host: str, port: int, lan: bool) -> VigiaServer:
    """Tenta a porta pedida; se estiver ocupada, usa uma livre."""
    try:
        server = VigiaServer((host, port), api, token, lan)
    except OSError:
        server = VigiaServer((host, 0), api, token, lan)
    return server
