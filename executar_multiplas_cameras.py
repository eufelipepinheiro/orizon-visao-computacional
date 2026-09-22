"""Executa câmeras da API combinando RTSP remoto e zonas locais."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from camera_api import CameraApiError, CameraRecord, fetch_cameras


DEFAULT_CAMERA_IDS = ("9", "13")
DEFAULT_BASE_URL = "https://unideographical-nonnocturnally-jarred.ngrok-free.dev"


def safe_access(access: str) -> str:
    """Remove usuário e senha da URL exibida no terminal."""
    parts = urlsplit(access)
    if not parts.scheme:
        return "<acesso configurado>"
    host = parts.hostname or ""
    if parts.port:
        host += f":{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, ""))


def find_monitor_script(project_root: Path, explicit: str | None = None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit).resolve())
    candidates.extend(
        [
            project_root
            / "orizon_teste_real"
            / "teste_real_orizon"
            / "yolo11objectdetection-track.py",
            project_root / "yolo11objectdetection-track.py",
        ]
    )
    for candidate in candidates:
        if candidate.is_file() and (candidate.parent / "best.pt").is_file():
            return candidate
    raise FileNotFoundError(
        "não encontrei yolo11objectdetection-track.py junto de best.pt"
    )


def load_local_config(config_dir: Path, camera_id: str) -> dict:
    path = config_dir / f"camera_{camera_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"configuração local não encontrada: {path}")
    with path.open("r", encoding="utf-8-sig") as file:
        config = json.load(file)
    if not isinstance(config.get("zonas"), dict) or not config["zonas"]:
        raise ValueError(f"{path.name} não possui zonas configuradas")
    return config


def prepare_config(local: dict, camera: CameraRecord, base_url: str) -> dict:
    """Copia o config local e injeta somente os dados vindos da API."""
    config = dict(local)
    config["camera_id"] = int(camera.camera_id) if camera.camera_id.isdigit() else camera.camera_id
    config["camera_source"] = camera.acesso
    config["backend_url"] = base_url.rstrip("/")
    config["carregar_zonas_backend"] = False
    config.setdefault("comodo", camera.nome)
    return config


def run_processes(specs: list[tuple[Path, Path]], monitor_script: Path) -> int:
    processes: list[subprocess.Popen] = []
    process_env = os.environ.copy()
    process_env.setdefault(
        "OPENCV_FFMPEG_CAPTURE_OPTIONS",
        "rtsp_transport;tcp|stimeout;5000000",
    )
    try:
        for camera_config, display_path in specs:
            print(f"[launcher] iniciando {display_path.name}")
            processes.append(
                subprocess.Popen(
                    [sys.executable, str(monitor_script), str(camera_config)],
                    cwd=str(monitor_script.parent),
                    env=process_env,
                )
            )
        return max((process.wait() for process in processes), default=0)
    except KeyboardInterrupt:
        print("\n[launcher] encerrando câmeras...")
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        return 130


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--listar-api", action="store_true")
    mode.add_argument("--executar-api", action="store_true")
    parser.add_argument("--base-url", default=os.getenv("ORIZON_BACKEND_URL", DEFAULT_BASE_URL))
    parser.add_argument("--endpoint", default="/api/cameras")
    parser.add_argument(
        "--camera-id",
        action="append",
        dest="camera_ids",
        help="ID a executar; pode ser repetido. Padrão: 9 e 13.",
    )
    parser.add_argument("--config-dir", help="Pasta dos camera_ID.json")
    parser.add_argument("--script", help="Caminho opcional do monitor YOLO")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    config_dir = (
        Path(args.config_dir).resolve()
        if args.config_dir
        else project_root / "config" / "cameras"
    )
    selected_ids = tuple(args.camera_ids or DEFAULT_CAMERA_IDS)

    try:
        cameras, warnings = fetch_cameras(args.base_url, args.endpoint)
    except CameraApiError as error:
        print(f"[api] não foi possível consultar as câmeras: {error}")
        return 2

    for warning in warnings:
        print(f"[api] AVISO: {warning}")

    by_id = {camera.camera_id: camera for camera in cameras}
    for camera in cameras:
        selected = "SELECIONADA" if camera.camera_id in selected_ids else "IGNORADA"
        print(
            f"[api] id={camera.camera_id} | {camera.nome} | {selected} | "
            f"acesso={safe_access(camera.acesso)}"
        )

    if args.listar_api:
        return 0

    try:
        monitor_script = find_monitor_script(project_root, args.script)
    except FileNotFoundError as error:
        print(f"[launcher] ERRO: {error}")
        return 2

    with tempfile.TemporaryDirectory(prefix="orizon_rtsp_") as temp_directory:
        specs: list[tuple[Path, Path]] = []
        for camera_id in selected_ids:
            camera = by_id.get(str(camera_id))
            if camera is None:
                print(f"[launcher] ERRO: câmera {camera_id} não veio da API")
                return 2
            if not camera.ativa:
                print(f"[launcher] câmera {camera_id} está inativa; ignorada")
                continue
            try:
                local = load_local_config(config_dir, str(camera_id))
            except (OSError, ValueError, json.JSONDecodeError) as error:
                print(f"[launcher] ERRO: {error}")
                return 2

            generated = prepare_config(local, camera, args.base_url)
            temp_path = Path(temp_directory) / f"camera_{camera_id}.json"
            temp_path.write_text(
                json.dumps(generated, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            specs.append((temp_path, config_dir / f"camera_{camera_id}.json"))

        print(f"[launcher] monitor: {monitor_script}")
        print(f"[launcher] configurações locais: {config_dir}")
        return run_processes(specs, monitor_script)


if __name__ == "__main__":
    raise SystemExit(main())
