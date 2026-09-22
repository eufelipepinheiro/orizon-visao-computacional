"""
zone_loader.py

Busca a calibração de cada zona (polígono + EPIs obrigatórios) direto do
backend, em vez de manter os pontos hardcoded no script principal.

Como funciona:
    Pra cada zona (ex: "MAQUINA_1"), sabemos o id_zona correspondente
    no banco (vem de ZONA_ID_MAP, em webhook_client.py -- é o mesmo
    mapa usado pra enviar as ocorrências, então fica uma fonte única de
    verdade). Fazemos GET /api/zona/{id} pra cada uma.

    O backend (model Zona.java) devolve algo como:
        {
          "id_zona": 3,
          "nome": "MAQUINA_1",
          "poligonos": [214, 21, 209, 464, 528, 453, 499, 29],
          "maquina": {"id_maquina": 1, ...},
          "epi": [
            {"id": 1, "epi": {"id_epi": 2, "nome": "epi_capacete", ...}}
          ]
        }

    Duas particularidades importantes desse formato (diferente do que
    a gente supunha antes de ver o código real do backend):
      1. "poligonos" é uma lista ACHATADA de números (x1,y1,x2,y2,...),
         não uma lista de pares [x,y]. Precisa desmembrar em pares.
      2. Não existe campo de resolução de referência na Zona -- então
         não dá pra saber com certeza em que resolução os pontos foram
         calibrados. Por enquanto, se a API não informar isso, ASSUME
         que os pontos já estão na resolução nativa da câmera atual
         (sem escala). Se isso causar zonas mal posicionadas, é sinal
         de que esse campo precisa ser adicionado no backend.

Se a API falhar (backend fora do ar, zona ainda não calibrada, id
faltando no ZONA_ID_MAP), cai pro fallback local -- os pontos que já
estão no config da câmera -- pra não travar a operação.
"""

import requests
import numpy as np

REQUEST_TIMEOUT = 5
VERBOSE = True


def _unflatten_polygon(poligonos_achatados):
    """[x1,y1,x2,y2,...] -> [[x1,y1],[x2,y2],...]"""
    pares = list(zip(poligonos_achatados[0::2], poligonos_achatados[1::2]))
    return pares


def load_zones_from_api(camera_width, camera_height, zona_id_map, api_url, fallback=None):
    """
    Retorna um dicionário no mesmo formato que o script principal já usa:
        {
          "MAQUINA_1": {"polygon": np.array(...), "epis_obrigatorios": {...}},
          ...
        }

    camera_width / camera_height: resolução real da câmera (pra escalar
        os pontos, quando a API informar a resolução de referência).
    zona_id_map: dict {nome_da_zona: id_zona ou None}
    api_url: raiz da API (ex: "https://webhook.site/xxx" em teste, ou
        "http://IP:8080" em produção).
    fallback: dict opcional com o mesmo formato de retorno, usado quando
        a API não responde ou a zona ainda não tem id_zona definido.
    """
    fallback = fallback or {}
    zonas = {}

    for zona_nome, id_zona in zona_id_map.items():
        if id_zona is None:
            if VERBOSE:
                print(f"[zone_loader] '{zona_nome}' sem id_zona -- usando fallback local")
            if zona_nome in fallback:
                zonas[zona_nome] = fallback[zona_nome]
            continue

        url = f"{api_url.rstrip('/')}/api/zona/{id_zona}"
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            pontos = _unflatten_polygon(data["poligonos"])

            # Zona.java não tem campo de resolução de referência hoje.
            # Se algum dia for adicionado, o código já aproveita; até
            # lá, assume que os pontos já estão na resolução da câmera.
            ref = data.get("resolucao_referencia")
            if ref:
                sx = camera_width / ref["largura"]
                sy = camera_height / ref["altura"]
            else:
                sx = sy = 1.0

            polygon_scaled = np.array(
                [[int(x * sx), int(y * sy)] for x, y in pontos],
                np.int32,
            )

            epis = {item["epi"]["nome"] for item in data.get("epi", []) if item.get("epi")}

            zonas[zona_nome] = {
                "polygon": polygon_scaled,
                "epis_obrigatorios": epis,
            }
            if VERBOSE:
                print(f"[zone_loader] '{zona_nome}' carregada da API (id_zona={id_zona})")

        except (requests.exceptions.RequestException, KeyError, ValueError, TypeError) as e:
            if VERBOSE:
                print(f"[zone_loader] falha ao buscar '{zona_nome}' da API: {e}")
            if zona_nome in fallback:
                if VERBOSE:
                    print(f"[zone_loader] usando fallback local pra '{zona_nome}'")
                zonas[zona_nome] = fallback[zona_nome]
            else:
                print(f"[zone_loader] AVISO: '{zona_nome}' sem fallback -- zona ficará indisponível")

    return zonas
