"""
zone_loader.py

Busca a calibração de cada zona (polígono + EPIs obrigatórios) direto do
backend por ID da câmera e converte para as classes treinadas no modelo YOLO (Roboflow).
"""

import requests
import numpy as np

REQUEST_TIMEOUT = 5
VERBOSE = True

# ==============================================================================
# TABELA DE TRADUÇÃO (DE: Backend Jhonatan -> PARA: Suas Classes YOLO Roboflow)
# ==============================================================================
EPI_MAP = {
    # Mapeamento por ID do Backend (Recomendado)
    2: "epi_oculos",                    # id_epi 2 -> Óculos de Proteção
    9: "epi_capacete",                  # id_epi 9 -> EPI capacete
    11: "colete",                       # id_epi 11 -> Colete
    3: "epi_protetor_auricular",        # id_epi 3 -> Protetor Auricular (Sugestão Roboflow)
    12: "epi_luva",                     # id_epi 12 -> EPI luva (Sugestão Roboflow)

    # Mapeamento por Nome do Backend (Fallback de Segurança)
    "Óculos de Proteção": "epi_oculos",
    "EPI capacete": "epi_capacete",
    "Colete": "colete",
    "Protetor Auricular": "epi_protetor_auricular",
    "EPI luva": "epi_luva",
}


def parse_poligonos(poligonos_data):
    """
    Suporta tanto a estrutura nova da API [{'x': 627, 'y': 365}]
    quanto a antiga achatada [x1, y1, x2, y2].
    """
    if not poligonos_data:
        return []
    
    if isinstance(poligonos_data[0], dict):
        return [[pt["x"], pt["y"]] for pt in poligonos_data if "x" in pt and "y" in pt]
    
    return list(zip(poligonos_data[0::2], poligonos_data[1::2]))


def load_zones_from_api(camera_width, camera_height, zona_id_map, api_url, fallback=None, camera_id=None):
    fallback = fallback or {}
    zonas = {}

    if camera_id is None:
        camera_id = 9 
        if VERBOSE:
            print(f"[zone_loader] AVISO: camera_id não informado. Assumindo: {camera_id}")

    api_data_list = []
    if camera_id is not None:
        url = f"{api_url.rstrip('/')}/api/zona/camera/{camera_id}"
        try:
            if VERBOSE:
                print(f"[zone_loader] Buscando zonas na API: {url}")
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            api_data_list = resp.json()
        except (requests.exceptions.RequestException, ValueError, TypeError) as e:
            if VERBOSE:
                print(f"[zone_loader] falha ao buscar zonas da câmera {camera_id} via API: {e}")

    if isinstance(api_data_list, dict):
        api_data_list = [api_data_list]

    # Mapeamento flexível por nome ou por índice de ordem
    api_zones_dict = {}
    for data in api_data_list:
        if isinstance(data, dict):
            nome_zona = data.get("nome")
            if nome_zona:
                api_zones_dict[nome_zona] = data

    # Se a API retornou zonas mas os nomes não batem com o JSON local, mapeamos por índice (ordem)
    lista_api_disponivel = list(api_data_list)

    for index, (zona_nome, id_zona_local) in enumerate(zona_id_map.items()):
        # Tenta achar pelo nome exato ou pega pelo índice correspondente na lista da API
        data = api_zones_dict.get(zona_nome)
        if not data and index < len(lista_api_disponivel):
            data = lista_api_disponivel[index]
            if VERBOSE:
                print(f"[zone_loader] Mapeamento por índice: associando '{zona_nome}' aos dados da API index {index}")

        if not data:
            if VERBOSE:
                print(f"[zone_loader] '{zona_nome}' não encontrada na API -- usando fallback local")
            if zona_nome in fallback:
                zonas[zona_nome] = fallback[zona_nome]
            continue

        try:
            pontos = parse_poligonos(data.get("poligonos", []))

            ref = data.get("resolucao") or data.get("resolucao_referencia") or {}
            ref_w = ref.get("largura", camera_width)
            ref_h = ref.get("altura", camera_height)

            sx = camera_width / ref_w if ref_w > 0 else 1.0
            sy = camera_height / ref_h if ref_h > 0 else 1.0

            polygon_scaled = np.array(
                [[int(x * sx), int(y * sy)] for x, y in pontos],
                np.int32
            )

            epis_traduzidos_yolo = set()

            for item in data.get("epi", []):
                epi_info = item.get("epi", {}) if isinstance(item, dict) and "epi" in item else item
                if isinstance(epi_info, dict):
                    id_epi = epi_info.get("id_epi")
                    nome_backend = epi_info.get("nome")

                    if id_epi in EPI_MAP:
                        epis_traduzidos_yolo.add(EPI_MAP[id_epi])
                    elif nome_backend in EPI_MAP:
                        epis_traduzidos_yolo.add(EPI_MAP[nome_backend])
                    elif nome_backend:
                        epis_traduzidos_yolo.add(nome_backend)

            zonas[zona_nome] = {
                "polygon": polygon_scaled,
                "epis_obrigatorios": epis_traduzidos_yolo
            }
            
            id_zona_backend = data.get("id_zona")
            if VERBOSE:
                print(f"[zone_loader] '{zona_nome}' carregada com sucesso do backend (id_zona={id_zona_backend}) | EPIs: {epis_traduzidos_yolo}")

        except (KeyError, ValueError, TypeError) as e:
            if VERBOSE:
                print(f"[zone_loader] erro ao processar dados da zona '{zona_nome}': {e}")
            if zona_nome in fallback:
                zonas[zona_nome] = fallback[zona_nome]

    return zonas