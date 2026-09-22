"""Abertura uniforme de webcam, câmera virtual, arquivo e RTSP."""

from __future__ import annotations

import os
import re
import time
from urllib.parse import urlsplit, urlunsplit

import cv2


def resolve_camera_source(config: dict):
    env_name = config.get("camera_source_env")
    if env_name:
        value = os.getenv(env_name)
        if not value:
            raise RuntimeError(f"A variável de ambiente '{env_name}' não foi definida.")
        return value

    if "camera_source" not in config:
        raise RuntimeError("Defina 'camera_source' ou 'camera_source_env' no JSON.")

    source = config["camera_source"]
    if isinstance(source, str) and source.isdigit():
        return int(source)
    return source


def safe_source_name(source) -> str:
    if not isinstance(source, str) or "://" not in source:
        return str(source)
    parts = urlsplit(source)
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    safe_path = re.sub(
        r"(?i)(password|passwd|pwd)=([^&/?]+)", r"\1=***", parts.path
    )
    safe_query = re.sub(
        r"(?i)(password|passwd|pwd)=([^&]+)", r"\1=***", parts.query
    )
    return urlunsplit((parts.scheme, f"{hostname}{port}", safe_path, safe_query, ""))


class ReconnectingVideoCapture:
    def __init__(self, source, *, reconnect_seconds: float = 2.0, reconnect_attempts: int = 0):
        self.source = source
        self.reconnect_seconds = max(0.2, float(reconnect_seconds))
        self.reconnect_attempts = max(0, int(reconnect_attempts))
        self.capture = None
        self._open()

    def _open(self) -> bool:
        self.release()
        if isinstance(self.source, str) and self.source.lower().startswith("rtsp://"):
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        backend = cv2.CAP_FFMPEG if isinstance(self.source, str) else cv2.CAP_ANY
        self.capture = cv2.VideoCapture(self.source, backend)
        if self.capture.isOpened():
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return True
        return False

    def is_opened(self) -> bool:
        return bool(self.capture and self.capture.isOpened())

    def get(self, property_id: int) -> float:
        return self.capture.get(property_id) if self.capture else 0.0

    def read(self):
        if self.capture:
            ok, frame = self.capture.read()
            if ok and frame is not None:
                return True, frame

        attempt = 0
        while self.reconnect_attempts == 0 or attempt < self.reconnect_attempts:
            attempt += 1
            print(f"[camera] sinal perdido; reconectando em {self.reconnect_seconds:.1f}s (tentativa {attempt})")
            time.sleep(self.reconnect_seconds)
            if not self._open():
                continue
            ok, frame = self.capture.read()
            if ok and frame is not None:
                print("[camera] conexão restabelecida")
                return True, frame
        return False, None

    def release(self) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None
