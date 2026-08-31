"""Cliente HTTP para enviar ocorrências e alertas ao backend Orizon.

Contrato confirmado no backend Spring:
- POST /api/ocorrencia cria a ocorrência.
- POST /api/alerta cria o alerta ligado ao id_ocorrencia retornado.
- Toda ocorrência precisa de id_zona e, no serviço atual, de id_funcionario.
"""

import threading
import time

import requests


# TESTE: as requisições aparecem ao vivo na página do Webhook.site.
# PRODUÇÃO: substitua somente esta URL pelo domínio atual do ngrok,
# sem acrescentar /api/ocorrencia ou /api/alerta no final.
BASE_URL = "https://webhook.site/719f4ecf-564f-44b5-bf90-441e86611495"
#BASE_URL = "https://unideographical-nonnocturnally-jarred.ngrok-free.dev"
MODO_TESTE_WEBHOOK = "webhook.site" in BASE_URL

# Preenchidos pelo script principal a partir do config da câmera.
ZONA_ID_MAP = {}
DEFAULT_FUNCIONARIO_ID = None

REQUEST_TIMEOUT = 6
VERBOSE = True
ALERTA_STATUS = "critico"
HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "ngrok-skip-browser-warning": "true",
}


def _post(path, payload):
    """Executa um POST e devolve o JSON, ou None quando falhar."""
    url = f"{BASE_URL.rstrip('/')}{path}"

    try:
        resp = requests.post(
            url,
            json=payload,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        if VERBOSE:
            print(f"[webhook] POST {path} -> status {resp.status_code}")

        resp.raise_for_status()

        if not resp.content:
            return None

        try:
            return resp.json()
        except ValueError:
            if VERBOSE:
                print(f"[webhook] resposta não é JSON: {resp.text[:300]}")
            return None

    except requests.exceptions.RequestException as erro:
        if VERBOSE:
            detalhe = ""
            resposta = getattr(erro, "response", None)
            if resposta is not None:
                detalhe = f" | resposta: {resposta.text[:500]}"
            print(f"[webhook] ERRO em POST {path}: {erro}{detalhe}")
        return None


def _funcionario_id(funcionario):
    """Usa o reconhecido; se não houver ID, usa o funcionário padrão."""
    if funcionario and funcionario.get("id_funcionario"):
        return funcionario["id_funcionario"]
    return DEFAULT_FUNCIONARIO_ID


def _notify_zone_status(zona_nome, status, epis_faltando, pose_info, funcionario):
    id_zona = ZONA_ID_MAP.get(zona_nome)

    if id_zona is None:
        if VERBOSE:
            print(
                f"[webhook] AVISO: '{zona_nome}' sem id_zona; "
                "ocorrência não enviada"
            )
        return

    id_funcionario = _funcionario_id(funcionario)
    if id_funcionario is None:
        if VERBOSE:
            print(
                "[webhook] AVISO: nenhum id_funcionario disponível; "
                "configure funcionario_padrao_id no JSON da câmera"
            )
        return

    data_hora = time.strftime("%Y-%m-%dT%H:%M:%S")

    ocorrencia_payload = {
        "data_hora": data_hora,
        "status": status,
        "zona": {"id_zona": id_zona},
        "funcionario": {"id_funcionario": id_funcionario},
    }

    resultado = _post("/api/ocorrencia", ocorrencia_payload)
    id_ocorrencia = resultado.get("id_ocorrencia") if isinstance(resultado, dict) else None

    if status != "BLOQUEADA":
        return

    # O Webhook.site normalmente não devolve o ID criado por um backend.
    # No teste usamos um ID fictício apenas para conseguir visualizar também
    # o POST /api/alerta. Em produção, vale somente o ID real da ocorrência.
    if not id_ocorrencia and MODO_TESTE_WEBHOOK:
        id_ocorrencia = 999

    if not id_ocorrencia:
        if VERBOSE:
            print("[webhook] ocorrência não retornou id_ocorrencia; alerta não enviado")
        return

    motivos = []
    if epis_faltando:
        motivos.append("EPI(s) faltando: " + ", ".join(epis_faltando))
    if pose_info and pose_info.get("postura_ok") is False:
        motivos.append("postura inadequada")
    if not motivos:
        motivos.append("Zona bloqueada")

    alerta_payload = {
        "mensagem": " | ".join(motivos),
        "status": ALERTA_STATUS,
        "data_hora": data_hora,
        "ocorrencia": {"id_ocorrencia": id_ocorrencia},
    }
    _post("/api/alerta", alerta_payload)


def notify_zone_status_async(
    zona_nome,
    status,
    epis_faltando=None,
    pose_info=None,
    funcionario=None,
):
    """Envia sem bloquear o loop de vídeo."""
    thread = threading.Thread(
        target=_notify_zone_status,
        args=(
            zona_nome,
            status,
            epis_faltando or [],
            pose_info or {},
            funcionario,
        ),
        daemon=True,
    )
    thread.start()
