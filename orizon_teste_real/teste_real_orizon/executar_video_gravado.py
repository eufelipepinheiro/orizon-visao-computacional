r"""Executa o monitoramento Orizon usando um arquivo de vídeo.

Este arquivo não altera o programa principal. Ele intercepta somente a abertura
da câmera e entrega um vídeo gravado ao ``yolo11objectdetection-track.py``.

Por segurança, o modo padrão:
  - não envia ocorrências ao backend;
  - não consulta zonas no backend;
  - não aciona o ESP32;
  - não exige reconhecimento facial.

Exemplo, executado dentro da pasta ``teste_real_orizon``:

    python .\executar_video_gravado.py `
      --video "C:\Videos\camera_9.mp4" `
      --config "..\..\config\cameras\camera_9.json"

Para testar também os envios reais:

    python .\executar_video_gravado.py `
      --video "C:\Videos\camera_9.mp4" `
      --config "..\..\config\cameras\camera_9.json" `
      --enviar-backend
"""

from __future__ import annotations

import argparse
import json
import runpy
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Executa o programa Orizon com um vídeo gravado no lugar da "
            "webcam ou do fluxo RTSP."
        )
    )
    parser.add_argument(
        "--video",
        required=True,
        help="Caminho do vídeo gravado (.mp4, .avi, .mkv etc.).",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="JSON que contém as zonas e os EPIs da câmera.",
    )
    parser.add_argument(
        "--programa",
        default=None,
        help=(
            "Programa principal. O padrão é yolo11objectdetection-track.py "
            "na mesma pasta deste arquivo."
        ),
    )
    parser.add_argument(
        "--enviar-backend",
        action="store_true",
        help="Permite o envio real de ocorrências, alertas e imagens.",
    )
    parser.add_argument(
        "--usar-zonas-backend",
        action="store_true",
        help="Permite consultar as zonas na API em vez de usar apenas o JSON.",
    )
    parser.add_argument(
        "--habilitar-esp32",
        action="store_true",
        help="Mantém o ESP32 habilitado durante o teste.",
    )
    parser.add_argument(
        "--manter-reconhecimento-facial",
        action="store_true",
        help="Mantém a exigência de reconhecimento facial definida no JSON.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Ao terminar, reinicia o vídeo automaticamente.",
    )
    parser.add_argument(
        "--pular-frames",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Processa um quadro a cada N quadros do vídeo. Use 3, por exemplo, "
            "se o vídeo estiver muito lento. Padrão: 1."
        ),
    )
    return parser


def _resolver(caminho: str, base: Path | None = None) -> Path:
    path = Path(caminho).expanduser()
    if not path.is_absolute() and base is not None:
        path = base / path
    return path.resolve()


def _carregar_config(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as arquivo:
            config = json.load(arquivo)
    except OSError as erro:
        raise SystemExit(f"[ERRO] Não foi possível ler o config: {erro}") from erro
    except json.JSONDecodeError as erro:
        raise SystemExit(f"[ERRO] JSON inválido em {path}: {erro}") from erro

    if not isinstance(config, dict):
        raise SystemExit("[ERRO] O arquivo de configuração precisa conter um objeto JSON.")
    if not isinstance(config.get("zonas", {}), dict):
        raise SystemExit("[ERRO] O campo 'zonas' do JSON precisa ser um objeto.")
    return config


def _criar_config_temporario(
    config_original: dict[str, Any],
    video: Path,
    usar_zonas_backend: bool,
    habilitar_esp32: bool,
    manter_reconhecimento_facial: bool,
) -> Path:
    config = dict(config_original)
    config["camera_source"] = str(video)
    config["carregar_zonas_backend"] = usar_zonas_backend
    config["esp32_habilitado"] = habilitar_esp32

    if not manter_reconhecimento_facial:
        config["exige_reconhecimento_facial"] = False

    temporario = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="orizon_video_teste_",
        encoding="utf-8",
        delete=False,
    )
    try:
        json.dump(config, temporario, ensure_ascii=False, indent=2)
        temporario.write("\n")
        return Path(temporario.name)
    finally:
        temporario.close()


class _CapturaDeVideo:
    """Proxy compatível com cv2.VideoCapture para arquivo local."""

    def __init__(
        self,
        captura_real: Any,
        cv2_module: Any,
        video: Path,
        loop: bool,
        pular_frames: int,
    ) -> None:
        self._cv2 = cv2_module
        self._video = video
        self._loop = loop
        self._pular_frames = pular_frames
        self._cap = captura_real(str(video))

    def isOpened(self) -> bool:  # noqa: N802 - mantém a API do OpenCV
        return bool(self._cap.isOpened())

    def read(self) -> tuple[bool, Any]:
        ok = False
        frame = None

        for _ in range(self._pular_frames):
            ok, frame = self._cap.read()
            if ok:
                continue

            if not self._loop:
                return False, None

            self._cap.set(self._cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
            if not ok:
                return False, None

        return ok, frame

    def get(self, propriedade: int) -> float:
        return float(self._cap.get(propriedade))

    def set(self, propriedade: int, valor: float) -> bool:
        return bool(self._cap.set(propriedade, valor))

    def release(self) -> None:
        self._cap.release()

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._cap, nome)


def _desativar_backend() -> tuple[Any, Any]:
    """Substitui os pontos de envio sem alterar arquivos do projeto."""
    import webhook_client

    funcao_original = getattr(webhook_client, "notify_zone_status_async", None)
    post_original = getattr(webhook_client, "_post", None)

    def apenas_mostrar(
        zona_nome: str,
        status: str,
        epis_faltando: list[str] | None = None,
        pose_info: dict[str, Any] | None = None,
        funcionario: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        print(
            "[teste sem backend] "
            f"zona={zona_nome} status={status} "
            f"faltando={epis_faltando or []} "
            f"funcionario={funcionario or 'padrão do config'}"
        )

    def post_falso(path: str, payload: dict[str, Any]) -> dict[str, int]:
        print(f"[teste sem backend] POST {path} ignorado: {payload}")
        return {"id_ocorrencia": 999}

    webhook_client.notify_zone_status_async = apenas_mostrar
    if post_original is not None:
        webhook_client._post = post_falso
    return funcao_original, post_original


def _usar_zonas_locais() -> Any:
    """Evita GET de zonas em versões antigas do programa principal."""
    import zone_loader

    original = getattr(zone_loader, "load_zones_from_api", None)

    def carregar_fallback(*args: Any, **kwargs: Any) -> dict[str, Any]:
        fallback = kwargs.get("fallback")
        if fallback is None and len(args) >= 5:
            fallback = args[4]
        print("[teste] usando zonas locais do JSON")
        return fallback or {}

    zone_loader.load_zones_from_api = carregar_fallback
    return original


def main() -> int:
    args = _parser().parse_args()
    if args.pular_frames < 1:
        raise SystemExit("[ERRO] --pular-frames precisa ser 1 ou maior.")

    pasta_script = Path(__file__).resolve().parent
    video = _resolver(args.video, Path.cwd())
    config_path = _resolver(args.config, Path.cwd())
    programa = _resolver(
        args.programa or "yolo11objectdetection-track.py",
        pasta_script,
    )

    for descricao, path in (
        ("vídeo", video),
        ("configuração", config_path),
        ("programa principal", programa),
    ):
        if not path.is_file():
            raise SystemExit(f"[ERRO] Arquivo de {descricao} não encontrado: {path}")

    config_original = _carregar_config(config_path)
    if not config_original.get("zonas"):
        print("[AVISO] O JSON não possui zonas. O vídeo abrirá sem validação por zona.")

    config_temporario = _criar_config_temporario(
        config_original=config_original,
        video=video,
        usar_zonas_backend=args.usar_zonas_backend,
        habilitar_esp32=args.habilitar_esp32,
        manter_reconhecimento_facial=args.manter_reconhecimento_facial,
    )

    import cv2

    captura_original = cv2.VideoCapture
    webhook_original = None
    post_original = None
    zona_loader_original = None
    argv_original = sys.argv[:]

    def abrir_video_gravado(*_: Any, **__: Any) -> _CapturaDeVideo:
        print(f"[teste] fonte substituída pelo vídeo: {video}")
        return _CapturaDeVideo(
            captura_real=captura_original,
            cv2_module=cv2,
            video=video,
            loop=args.loop,
            pular_frames=args.pular_frames,
        )

    try:
        cv2.VideoCapture = abrir_video_gravado

        if not args.enviar_backend:
            webhook_original, post_original = _desativar_backend()
        if not args.usar_zonas_backend:
            zona_loader_original = _usar_zonas_locais()

        print("\n=== TESTE ORIZON COM VÍDEO GRAVADO ===")
        print(f"Vídeo:   {video}")
        print(f"Config:  {config_path}")
        print(f"Zonas:   {', '.join(config_original.get('zonas', {})) or 'nenhuma'}")
        print(f"Backend: {'ATIVO' if args.enviar_backend else 'DESATIVADO'}")
        print(f"ESP32:   {'ATIVO' if args.habilitar_esp32 else 'DESATIVADO'}")
        print("Pressione Q na janela do vídeo para encerrar.\n")

        sys.argv = [str(programa), str(config_temporario)]
        runpy.run_path(str(programa), run_name="__main__")
        return 0
    except KeyboardInterrupt:
        print("\n[teste] encerrado pelo usuário")
        return 0
    except SystemExit as erro:
        codigo = erro.code
        return codigo if isinstance(codigo, int) else 1
    finally:
        sys.argv = argv_original
        cv2.VideoCapture = captura_original

        if webhook_original is not None:
            import webhook_client

            webhook_client.notify_zone_status_async = webhook_original
            if post_original is not None:
                webhook_client._post = post_original

        if zona_loader_original is not None:
            import zone_loader

            zone_loader.load_zones_from_api = zona_loader_original

        try:
            config_temporario.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
