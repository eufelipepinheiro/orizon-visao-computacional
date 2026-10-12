"""
zone_loader_frames.py

Busca a calibração de cada zona (polígono + EPIs obrigatórios) direto do
backend e converte para as classes treinadas no modelo YOLO (Roboflow).
"""

from __future__ import annotations

from typing import Any
import numpy as np
import requests

REQUEST_TIMEOUT = 5
VERBOSE = True

# ==============================================================================
# TABELA DE TRADUÇÃO (DE: Backend -> PARA: Suas Classes YOLO Roboflow)
# ==============================================================================
EPI_MAP = {
    # Mapeamento por ID do Backend
    2: "epi_oculos",                 # id_epi 2 -> Óculos de Proteção
    9: "epi_capacete",               # id_epi 9 -> EPI capacete
    11: "colete",                    # id_epi 11 -> Colete
    3: "epi_protetor_auricular",     # id_epi 3 -> Protetor Auricular
    12: "epi_luva",                  # id_epi 12 -> EPI luva

    # Mapeamento por Nome do Backend
    "Óculos de Proteção": "epi_oculos",
    "EPI capacete": "epi_capacete",
    "Colete": "colete",
    "Protetor Auricular": "epi_protetor_auricular",
    "EPI luva": "epi_luva",
}


def parse_poligonos(poligonos_data: list[Any]) -> list[list[int]]:
    if not poligonos_data:
        return []

    # Formato 1: Lista de dicionários [{"x": 10, "y": 20}, ...]
    if isinstance(poligonos_data[0], dict):
        return [
            [int(pt["x"]), int(pt["y"])]
            for pt in poligonos_data
            if "x" in pt and "y" in pt
        ]

    # Formato 2: Lista de pares [[10, 20], [30, 40], ...]
    if isinstance(poligonos_data[0], (list, tuple)):
        return [[int(pt[0]), int(pt[1])] for pt in poligonos_data if len(pt) >= 2]

    # Formato 3: Lista linear [x1, y1, x2, y2, ...]
    return [
        [int(x), int(y)]
        for x, y in zip(poligonos_data[0::2], poligonos_data[1::2])
    ]


def _processa_dados_zona(
    data: dict[str, Any], camera_width: int, camera_height: int
) -> dict[str, Any] | None:
    pontos = parse_poligonos(data.get("poligonos") or data.get("polygon") or [])
    if not pontos:
        return None

    ref = data.get("resolucao") or data.get("resolucao_referencia") or {}
    ref_w = ref.get("largura") if isinstance(ref, dict) else None
    ref_h = ref.get("altura") if isinstance(ref, dict) else None

    ref_w = ref_w or camera_width
    ref_h = ref_h or camera_height

    sx = camera_width / ref_w if ref_w > 0 else 1.0
    sy = camera_height / ref_h if ref_h > 0 else 1.0

    polygon_scaled = np.array(
        [[int(x * sx), int(y * sy)] for x, y in pontos],
        np.int32
    )

    epis_traduzidos_yolo = set()
    epis_raw = data.get("epi") or data.get("epis") or data.get("epis_obrigatorios") or []

    for item in epis_raw:
        epi_info = item.get("epi", {}) if isinstance(item, dict) and "epi" in item else item
        if isinstance(epi_info, dict):
            id_epi = epi_info.get("id_epi") or epi_info.get("id")
            nome_backend = epi_info.get("nome")

            if id_epi in EPI_MAP:
                epis_traduzidos_yolo.add(EPI_MAP[id_epi])
            elif nome_backend in EPI_MAP:
                epis_traduzidos_yolo.add(EPI_MAP[nome_backend])
            elif nome_backend:
                epis_traduzidos_yolo.add(nome_backend)
        elif isinstance(epi_info, (int, str)):
            if epi_info in EPI_MAP:
                epis_traduzidos_yolo.add(EPI_MAP[epi_info])
            else:
                epis_traduzidos_yolo.add(str(epi_info))

    return {
        "polygon": polygon_scaled,
        "epis_obrigatorios": epis_traduzidos_yolo
    }


def load_zones_from_api(
    camera_width: int,
    camera_height: int,
    zona_id_map: dict[str, int | None],
    api_url: str,
    fallback: dict[str, Any] | None = None,
    camera_id: str | None = None
) -> dict[str, Any]:
    fallback = fallback or {}
    zonas = {}

    headers = {
        "Accept": "application/json",
        "ngrok-skip-browser-warning": "true",
    }

    # 1. Busca todas as zonas associadas a essa câmera na API
    if camera_id is not None:
        endpoints_camera = [
            f"{api_url.rstrip('/')}/api/camera/{camera_id}/zonas",
            f"{api_url.rstrip('/')}/api/zona/camera/{camera_id}",
            f"{api_url.rstrip('/')}/api/zonas/camera/{camera_id}",
            f"{api_url.rstrip('/')}/api/zonas?camera_id={camera_id}"
        ]

        for url in endpoints_camera:
            try:
                if VERBOSE:
                    print(f"[zone_loader] Tentando buscar zonas da câmera {camera_id} em: {url}")
                resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    data = resp.json()
                    lista_zonas = []
                    if isinstance(data, list):
                        lista_zonas = data
                    elif isinstance(data, dict):
                        lista_zonas = data.get("zonas") or data.get("data") or []

                    if lista_zonas:
                        for z_item in lista_zonas:
                            z_nome = z_item.get("nome") or z_item.get("nome_zona")
                            z_id = z_item.get("id_zona") or z_item.get("id")
                            if z_nome:
                                if z_id and zona_id_map is not None:
                                    zona_id_map[z_nome] = z_id
                                processed = _processa_dados_zona(z_item, camera_width, camera_height)
                                if processed:
                                    zonas[z_nome] = processed
                                    print(f"[zone_loader] SUCESSO! Zona '{z_nome}' carregada via API da Câmera {camera_id}")
                        if zonas:
                            return zonas
            except Exception as e:
                if VERBOSE:
                    print(f"[zone_loader] Tentativa em {url} falhou: {e}")

    # 2. Busca por id_zona individual caso a rota por câmera não retorne
    for zona_nome, id_zona in zona_id_map.items():
        if id_zona is None:
            if VERBOSE:
                print(f"[zone_loader] '{zona_nome}' sem id_zona -- usando fallback local")
            if zona_nome in fallback:
                zonas[zona_nome] = fallback[zona_nome]
            continue

        url = f"{api_url.rstrip('/')}/api/zona/{id_zona}"
        try:
            if VERBOSE:
                print(f"[zone_loader] Buscando zona '{zona_nome}' (id_zona={id_zona}) em: {url}")
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            processed = _processa_dados_zona(data, camera_width, camera_height)
            if processed:
                zonas[zona_nome] = processed
                if VERBOSE:
                    print(f"[zone_loader] '{zona_nome}' carregada (id_zona={id_zona}) | EPIs para YOLO: {processed['epis_obrigatorios']}")
            else:
                raise ValueError("Polígono ausente ou inválido na resposta da API")

        except Exception as e:
            if VERBOSE:
                print(f"[zone_loader] Falha ao buscar '{zona_nome}' (id={id_zona}) da API: {e}")
            if zona_nome in fallback:
                if VERBOSE:
                    print(f"[zone_loader] Usando fallback local para '{zona_nome}'")
                zonas[zona_nome] = fallback[zona_nome]

    # 3. Fallback local se nenhuma zona for obtida
    if not zonas and fallback:
        print("[zone_loader] Nenhuma zona obtida do backend. Usando fallback local.")
        return fallback

    return zonas