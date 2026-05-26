"""
DTC e-Bus Pass – Async frontend server
Uses asyncio (zero threads) to avoid the Python 3.14 Windows threading crash.
"""
import asyncio
import os
import sys
import mimetypes
import urllib.parse
import socket

# Fix slow reverse-DNS lookups on Windows
socket.getfqdn      = lambda *a, **k: "127.0.0.1"
socket.gethostbyaddr = lambda *a, **k: ("127.0.0.1", [], ["127.0.0.1"])

HOST = "127.0.0.1"
try:
    ROOT = os.path.dirname(os.path.abspath(__file__))
except Exception:
    ROOT = os.getcwd()

# ── MIME types (Windows mimetypes misses SVG, WOFF, etc.) ────────────────────
MIME = {
    ".svg":   "image/svg+xml",
    ".svgz":  "image/svg+xml",
    ".htm":   "text/html; charset=utf-8",
    ".html":  "text/html; charset=utf-8",
    ".css":   "text/css; charset=utf-8",
    ".js":    "application/javascript",
    ".json":  "application/json",
    ".png":   "image/png",
    ".jpg":   "image/jpeg",
    ".jpeg":  "image/jpeg",
    ".gif":   "image/gif",
    ".ico":   "image/x-icon",
    ".woff":  "font/woff",
    ".woff2": "font/woff2",
    ".ttf":   "font/ttf",
    ".eot":   "application/vnd.ms-fontobject",
    ".pdf":   "application/pdf",
    ".xml":   "application/xml",
    ".txt":   "text/plain; charset=utf-8",
}

REDIRECTS = {
    "/":           "/index.html",
    "/viewEPass":  "/viewEBPass.html",
    "/viewEBPass": "/viewEBPass.html",
}

def guess_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in MIME:
        return MIME[ext]
    mt, _ = mimetypes.guess_type(path)
    return mt or "application/octet-stream"

def make_response(status: int, reason: str, mime: str, body: bytes,
                  extra: str = "") -> bytes:
    headers = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {mime}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Access-Control-Allow-Origin: *\r\n"
        f"Cache-Control: no-store\r\n"
        f"Connection: close\r\n"
        f"{extra}"
        f"\r\n"
    )
    return headers.encode("utf-8") + body

# ── Request handler ────────────────────────────────────────────────────────────
async def handle(reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter) -> None:
    try:
        # Read request headers (stop at blank line)
        raw = b""
        try:
            while b"\r\n\r\n" not in raw:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=10.0)
                if not chunk:
                    break
                raw += chunk
                if len(raw) > 131072:   # 128 KB safety limit
                    break
        except asyncio.TimeoutError:
            return

        if not raw:
            return

        # Parse request line
        first = raw.split(b"\r\n")[0].decode("utf-8", errors="replace")
        parts = first.split()
        if len(parts) < 2:
            return
        method   = parts[0].upper()
        raw_path = parts[1]

        # Split path from query string
        if "?" in raw_path:
            path_enc, qs = raw_path.split("?", 1)
            qs = "?" + qs
        else:
            path_enc, qs = raw_path, ""

        path = urllib.parse.unquote(path_enc).rstrip("/") or "/"

        # CORS pre-flight
        if method == "OPTIONS":
            resp = make_response(204, "No Content", "text/plain", b"",
                                 "Access-Control-Allow-Methods: GET, OPTIONS\r\n"
                                 "Access-Control-Allow-Headers: Content-Type\r\n")
            writer.write(resp)
            await writer.drain()
            return

        # Redirects
        if path in REDIRECTS:
            dest = REDIRECTS[path] + qs
            resp = make_response(302, "Found", "text/plain", b"",
                                 f"Location: {dest}\r\n")
            writer.write(resp)
            await writer.drain()
            return

        # Serve static files (GET only)
        if method != "GET":
            writer.write(make_response(405, "Method Not Allowed",
                                       "text/plain", b"Method Not Allowed"))
            await writer.drain()
            return

        # Resolve file path safely
        rel       = path.lstrip("/")
        file_path = os.path.normpath(os.path.join(ROOT, rel))

        # Directory traversal guard
        if not file_path.startswith(ROOT):
            writer.write(make_response(403, "Forbidden",
                                       "text/plain", b"Forbidden"))
            await writer.drain()
            return

        # If directory → try index.html
        if os.path.isdir(file_path):
            file_path = os.path.join(file_path, "index.html")

        if os.path.isfile(file_path):
            with open(file_path, "rb") as fh:
                body = fh.read()
            mime = guess_mime(file_path)
            writer.write(make_response(200, "OK", mime, body))
            print(f"  200  {path}", flush=True)
        else:
            body = f"404 Not Found: {path}".encode()
            writer.write(make_response(404, "Not Found",
                                       "text/plain; charset=utf-8", body))
            print(f"  404  {path}", flush=True)

        await writer.drain()

    except ConnectionResetError:
        pass          # Browser closed tab – totally normal
    except Exception as exc:
        print(f"  [ERR] {exc}", flush=True)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

# ── Entry point ────────────────────────────────────────────────────────────────
async def run():
    server = None
    bound_port = None

    for port in [8000, 8080, 9000]:
        try:
            server = await asyncio.start_server(handle, HOST, port)
            bound_port = port
            break
        except OSError as exc:
            print(f"  Port {port} busy ({exc}), trying next…", flush=True)

    if server is None:
        print("ERROR: Could not bind to ports 8000 / 8080 / 9000.", flush=True)
        sys.exit(1)

    print("=" * 57, flush=True)
    print("  DTC e-Bus Pass  –  Frontend Server", flush=True)
    print(f"  Serving : {ROOT}", flush=True)
    print(flush=True)
    print(f"  Home    : http://localhost:{bound_port}/index.html", flush=True)
    print(f"  ePass   : http://localhost:{bound_port}/viewEBPass.html"
          f"?passno=7502032600973", flush=True)
    print(f"  Admin   : http://localhost:{bound_port}/registeredUsers.html",
          flush=True)
    print(flush=True)
    print("  Press Ctrl+C to stop.", flush=True)
    print("=" * 57, flush=True)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nServer stopped.", flush=True)
