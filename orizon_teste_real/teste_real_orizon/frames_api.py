"""Snapshots compartilhados entre processos. Servidor de teste local, não produção."""
import argparse
import hmac
import json
import os
import re
import tempfile
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

FRAME_DIR = Path(__file__).resolve().parent / "frames_temporarios"


class FramePublisher:
    def __init__(self, camera_id, directory=FRAME_DIR, interval=1.0):
        self.camera_id = str(camera_id)
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", self.camera_id):
            raise ValueError("Defina camera_id numérico ou alfanumérico no JSON")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.interval = max(1.0, float(interval))
        self.last = float("-inf")

    def publish(self, frame):
        now = time.monotonic()
        if now - self.last < self.interval:
            return False
        self.last = now
        import cv2
        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return False
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.directory, suffix=".tmp", delete=False) as f:
                temporary = Path(f.name)
                f.write(jpeg.tobytes())
            os.replace(temporary, self.directory / (self.camera_id + ".jpg"))
            return True
        except OSError as error:
            print(f"[frames] câmera {self.camera_id}: falha ao publicar ({type(error).__name__})")
            return False
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def make_server(host="127.0.0.1", port=5001, *, directory=FRAME_DIR,
                token="", origin="", max_age=5.0):
    if host not in ("127.0.0.1", "localhost") and not token:
        raise ValueError("Para acesso pela rede, defina ORIZON_FRAMES_TOKEN")
    directory = Path(directory)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body=b"", mime="application/json", extra=None):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("X-Content-Type-Options", "nosniff")
            if origin and self.headers.get("Origin") == origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Headers", "Authorization")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.reply(204)

        def do_GET(self):
            if token and not hmac.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + token):
                self.reply(401, b'{"erro":"nao autorizado"}')
                return
            match = re.fullmatch(r"/api/cameras/([a-zA-Z0-9_-]+)/frame", urlsplit(self.path).path)
            if not match:
                self.reply(404, b'{"erro":"rota inexistente"}')
                return
            try:
                with (directory / (match[1] + ".jpg")).open("rb") as f:
                    timestamp = os.fstat(f.fileno()).st_mtime
                    if time.time() - timestamp > max_age:
                        self.reply(503, b'{"erro":"frame desatualizado"}')
                        return
                    body = f.read()
            except OSError:
                self.reply(503, b'{"erro":"camera sem frame disponivel"}')
                return
            self.reply(200, body, "image/jpeg", {"X-Frame-Timestamp": str(timestamp)})

    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--origin", default="", help="Origem exata do frontend, se acesso direto")
    args = parser.parse_args()
    try:
        server = make_server(args.host, args.port, token=os.getenv("ORIZON_FRAMES_TOKEN", ""), origin=args.origin)
    except (ValueError, OSError) as error:
        parser.exit(2, f"[frames] {error}\n")
    print(f"[frames] GET http://{args.host}:{args.port}/api/cameras/9/frame", flush=True)
    print("[frames] Ctrl+C encerra. Sem imagem recente: HTTP 503.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
