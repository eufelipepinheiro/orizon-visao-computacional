"""Envio assíncrono de ocorrências e alertas ao backend Orizon."""

from __future__ import annotations

import threading
import time
from typing import Any

import requests


BASE_URL = "https://unideographical-nonnocturnally-jarred.ngrok-free.dev"
ZONA_ID_MAP: dict[str, int | None] = {}
DEFAULT_FUNCIONARIO_ID: int | None = None
CAMERA_ID: str | None = None
INCLUIR_CAMERA_PAYLOAD = False

REQUEST_TIMEOUT = 6
VERBOSE = True


def configure(
    *,
    base_url: str | None = None,
    camera_id: str | None = None,
    funcionario_padrao_id: int | None = None,
    incluir_camera_payload: bool = False,
) -> None:
    """Aplica a configuração específica da instância da câmera."""
    global BASE_URL, CAMERA_ID, DEFAULT_FUNCIONARIO_ID, INCLUIR_CAMERA_PAYLOAD

    if base_url:
        BASE_URL = base_url.rstrip("/")
    CAMERA_ID = camera_id
    DEFAULT_FUNCIONARIO_ID = funcionario_padrao_id
    INCLUIR_CAMERA_PAYLOAD = incluir_camera_payload


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "ngrok-skip-browser-warning": "true",
    }
    if CAMERA_ID:
        headers["X-Camera-Id"] = CAMERA_ID
    return headers


def _post(path: str, payload: dict[str, Any]):
    url = f"{BASE_URL.rstrip('/')}{path}"
    try:
        response = requests.post(
            url,
            json=payload,
            headers=_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        if VERBOSE:
            print(f"[webhook] POST {path} -> status {response.status_code}")
        if not response.ok:
            if VERBOSE:
                print(f"[webhook] resposta de erro: {response.text[:500]}")
            return None
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return None
    except requests.exceptions.RequestException as error:
        if VERBOSE:
            print(f"[webhook] ERRO em POST {path}: {error}")
        return None


def _funcionario_id(funcionario: dict[str, Any] | None) -> int | None:
    if funcionario and funcionario.get("id_funcionario"):
        return int(funcionario["id_funcionario"])
    return DEFAULT_FUNCIONARIO_ID


def _notify_zone_status(
    zona_nome: str,
    status: str,
    epis_faltando: list[str],
    pose_info: dict[str, Any],
    funcionario: dict[str, Any] | None,
) -> None:
    id_zona = ZONA_ID_MAP.get(zona_nome)
    if id_zona is None:
        if VERBOSE:
            print(f"[webhook] AVISO: '{zona_nome}' sem id_zona; envio ignorado")
        return

    id_funcionario = _funcionario_id(funcionario)
    if id_funcionario is None:
        if VERBOSE:
            print("[webhook] AVISO: nenhum id_funcionario disponível; envio ignorado")
        return

    data_hora = time.strftime("%Y-%m-%dT%H:%M:%S")
    ocorrencia_payload: dict[str, Any] = {
        "data_hora": data_hora,
        "status": status,
        "zona": {"id_zona": id_zona},
        "funcionario": {"id_funcionario": id_funcionario},
    }
    if CAMERA_ID and INCLUIR_CAMERA_PAYLOAD:
        ocorrencia_payload["camera_id"] = CAMERA_ID

    resultado = _post("/api/ocorrencia", ocorrencia_payload)

    if status != "BLOQUEADA":
        return

    id_ocorrencia = (
        resultado.get("id_ocorrencia") if isinstance(resultado, dict) else None
    )
    modo_webhook_site = "webhook.site" in BASE_URL
    if not id_ocorrencia and modo_webhook_site:
        id_ocorrencia = 999

    if not id_ocorrencia:
        if VERBOSE:
            print("[webhook] ocorrência não retornou id_ocorrencia; alerta não enviado")
        return

    motivos: list[str] = []
    if epis_faltando:
        motivos.append("EPI(s) faltando: " + ", ".join(epis_faltando))
    if pose_info and pose_info.get("postura_ok") is False:
        motivos.append("postura inadequada")
    if not motivos:
        motivos.append("Zona bloqueada")

    alerta_payload = {
        "mensagem": " | ".join(motivos),
        "status": "ALTA",
        "data_hora": data_hora,
        "ocorrencia": {"id_ocorrencia": id_ocorrencia},
    }
    _post("/api/alerta", alerta_payload)


def notify_zone_status_async(
    zona_nome: str,
    status: str,
    epis_faltando: list[str] | None = None,
    pose_info: dict[str, Any] | None = None,
    funcionario: dict[str, Any] | None = None,
) -> None:
    thread = threading.Thread(
        target=_notify_zone_status,
        args=(zona_nome, status, epis_faltando or [], pose_info or {}, funcionario),
        daemon=True,
    )
    thread.start()
