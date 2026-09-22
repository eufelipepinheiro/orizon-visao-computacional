"""Grava o vídeo bruto da câmera 9, sem zonas, YOLO ou webhooks."""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from pathlib import Path

import cv2

from camera_api import CameraApiError, fetch_cameras


DEFAULT_BASE_URL = "https://unideographical-nonnocturnally-jarred.ngrok-free.dev"
CAMERA_ID = "9"


def normalize_base_url(value: str) -> str:
    """Aceita domínio puro ou uma URL com endpoint colocado por engano."""
    base_url = value.strip().rstrip("/")
    suffixes = (
        "/api/cameras",
        "/api/camera",
        "/api/ocorrencia",
        "/api/alerta",
    )
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if base_url.lower().endswith(suffix):
                base_url = base_url[: -len(suffix)].rstrip("/")
                changed = True
                break
    return base_url


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--duracao",
        type=float,
        default=60,
        help="Segundos de gravação; use 0 para gravar até pressionar q.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("ORIZON_BACKEND_URL", DEFAULT_BASE_URL),
    )
    parser.add_argument("--sem-preview", action="store_true")
    parser.add_argument("--saida", help="Caminho opcional do arquivo MP4")
    args = parser.parse_args()

    base_url = normalize_base_url(args.base_url)
    try:
        cameras, avisos = fetch_cameras(base_url, "/api/cameras")
    except CameraApiError as error:
        print(f"[ERRO] Não foi possível consultar /api/cameras: {error}")
        return 2

    for aviso in avisos:
        print(f"[AVISO] {aviso}")

    camera = next(
        (item for item in cameras if item.camera_id == CAMERA_ID and item.ativa),
        None,
    )
    if camera is None:
        print("[ERRO] A câmera 9 não foi encontrada ou está inativa.")
        return 2

    os.environ.setdefault(
        "OPENCV_FFMPEG_CAPTURE_OPTIONS",
        "rtsp_transport;tcp|stimeout;5000000",
    )

    print("[camera 9] Abrindo transmissão RTSP...")
    cap = cv2.VideoCapture(camera.acesso, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("[ERRO] Não foi possível abrir a câmera 9.")
        return 2

    ok, primeiro_frame = cap.read()
    if not ok or primeiro_frame is None:
        cap.release()
        print("[ERRO] A câmera 9 abriu, mas não entregou imagem.")
        return 2

    altura, largura = primeiro_frame.shape[:2]
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not 1 <= fps <= 60:
        fps = 20.0

    if args.saida:
        arquivo_saida = Path(args.saida).expanduser().resolve()
    else:
        pasta = Path(__file__).resolve().parent / "gravacoes"
        nome = datetime.now().strftime("camera_9_%Y%m%d_%H%M%S.mp4")
        arquivo_saida = pasta / nome
    arquivo_saida.parent.mkdir(parents=True, exist_ok=True)

    writer = cv2.VideoWriter(
        str(arquivo_saida),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (largura, altura),
    )
    if not writer.isOpened():
        cap.release()
        print("[ERRO] Não foi possível criar o arquivo MP4.")
        return 2

    inicio = time.monotonic()
    frames = 0
    falhas_seguidas = 0
    print(
        f"[GRAVANDO] {largura}x{altura} a {fps:.1f} FPS. "
        "Pressione q na imagem ou Ctrl+C no terminal para encerrar."
    )

    try:
        frame = primeiro_frame
        while True:
            writer.write(frame)
            frames += 1

            if not args.sem_preview:
                cv2.imshow("Camera 9 - gravacao sem zonas", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            if args.duracao > 0 and time.monotonic() - inicio >= args.duracao:
                break

            ok, frame = cap.read()
            if ok and frame is not None:
                falhas_seguidas = 0
                continue

            falhas_seguidas += 1
            if falhas_seguidas >= 5:
                print("[AVISO] Sinal perdido; encerrando a gravação.")
                break
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[INFO] Gravação interrompida pelo usuário.")
    finally:
        writer.release()
        cap.release()
        cv2.destroyAllWindows()

    segundos = max(time.monotonic() - inicio, 0.001)
    print(f"[OK] Vídeo salvo em: {arquivo_saida}")
    print(f"[OK] {frames} frames gravados em {segundos:.1f} segundos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
