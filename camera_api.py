"""Leitura tolerante do cadastro de câmeras do backend Orizon."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


REQUEST_TIMEOUT = 10


class CameraApiError(RuntimeError):
    pass


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", text.lower())


ID_KEYS = {"id", "cameraid", "idcamera", "idcameras"}
ACCESS_KEYS = {
    "acesso",
    "cameraaccess",
    "camerasource",
    "endereco",
    "link",
    "rtsp",
    "stream",
    "streamurl",
    "url",
    "urlacesso",
    "urlrtsp",
}
NAME_KEYS = {"camera", "cameraname", "name", "nome", "nomecamera"}
DESCRIPTION_KEYS = {"description", "descricao", "descricaocamera"}
ACTIVE_KEYS = {"active", "ativa", "ativo", "enabled", "habilitada", "habilitado"}
STATUS_KEYS = {"status", "situacao"}
ZONE_KEYS = {"zones", "zonas"}
CONTAINER_KEYS = {
    "camera",
    "cameras",
    "content",
    "data",
    "dados",
    "items",
    "result",
    "results",
}


@dataclass(frozen=True)
class CameraRecord:
    camera_id: str
    acesso: str
    nome: str
    descricao: str | None = None
    ativa: bool = True
    zonas: Any = None
    original: dict[str, Any] | None = None


def _mapped(row: dict[str, Any]) -> dict[str, Any]:
    return {_key(key): value for key, value in row.items()}


def _first(fields: dict[str, Any], aliases: set[str], default=None):
    for alias in aliases:
        value = fields.get(alias)
        if value is not None and value != "":
            return value
    return default


def _access_value(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        nested = _mapped(value)
        candidate = _first(nested, ACCESS_KEYS)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _active_value(fields: dict[str, Any]) -> bool:
    value = _first(fields, ACTIVE_KEYS)
    if value is None:
        status = _first(fields, STATUS_KEYS)
        if status is None:
            return True
        return _key(status) not in {"0", "false", "inativa", "inativo", "offline", "desabilitada", "desabilitado"}
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return _key(value) not in {"0", "false", "nao", "inativa", "inativo", "offline"}


def _looks_like_camera(row: dict[str, Any]) -> bool:
    fields = _mapped(row)
    return bool(set(fields) & ACCESS_KEYS) or (
        bool(set(fields) & ID_KEYS) and bool(set(fields) & NAME_KEYS)
    )


def extract_camera_rows(payload: Any) -> list[dict[str, Any]]:
    """Aceita lista direta, wrappers comuns e respostas paginadas do Spring."""
    if isinstance(payload, list):
        rows = [item for item in payload if isinstance(item, dict)]
        if rows:
            return rows

    if not isinstance(payload, dict):
        raise ValueError("A resposta de /api/cameras não é uma lista nem um objeto JSON.")

    fields = _mapped(payload)
    for key in CONTAINER_KEYS:
        if key in fields:
            try:
                return extract_camera_rows(fields[key])
            except ValueError:
                pass

    # Também cobre Spring HATEOAS: {"_embedded": {"cameras": [...]}}.
    for value in payload.values():
        if isinstance(value, (dict, list)):
            try:
                rows = extract_camera_rows(value)
            except ValueError:
                continue
            if rows and any(_looks_like_camera(row) for row in rows):
                return rows

    if _looks_like_camera(payload):
        return [payload]

    raise ValueError("Não encontrei uma coleção de câmeras na resposta da API.")


def normalize_camera(row: dict[str, Any], index: int = 0) -> CameraRecord:
    fields = _mapped(row)
    raw_access = _first(fields, ACCESS_KEYS)
    acesso = _access_value(raw_access)
    if not acesso:
        raise ValueError(f"câmera #{index + 1} sem campo de acesso/URL RTSP")

    camera_id = str(_first(fields, ID_KEYS, index + 1))
    nome = str(_first(fields, NAME_KEYS, f"Camera {camera_id}"))
    descricao_value = _first(fields, DESCRIPTION_KEYS)
    zonas = _first(fields, ZONE_KEYS)

    return CameraRecord(
        camera_id=camera_id,
        acesso=acesso,
        nome=nome,
        descricao=str(descricao_value) if descricao_value is not None else None,
        ativa=_active_value(fields),
        zonas=zonas,
        original=row,
    )


def normalize_cameras(payload: Any) -> tuple[list[CameraRecord], list[str]]:
    cameras: list[CameraRecord] = []
    warnings: list[str] = []
    for index, row in enumerate(extract_camera_rows(payload)):
        try:
            cameras.append(normalize_camera(row, index))
        except ValueError as error:
            warnings.append(str(error))
    return cameras, warnings


def fetch_cameras(base_url: str, endpoint: str = "/api/cameras") -> tuple[list[CameraRecord], list[str]]:
    try:
        import requests
    except ImportError as error:
        raise CameraApiError("instale a dependência 'requests'") from error

    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        response = requests.get(
            url,
            headers={"Accept": "application/json", "ngrok-skip-browser-warning": "true"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return normalize_cameras(response.json())
    except requests.RequestException as error:
        raise CameraApiError(str(error)) from error
    except ValueError as error:
        raise CameraApiError(f"resposta JSON inválida: {error}") from error
