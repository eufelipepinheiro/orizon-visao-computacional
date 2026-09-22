"""
webhook_client.py

Envia os eventos de status das zonas (EPI + pose/liveness) para o backend.

FLUXO (baseado no schema real do backend Spring Boot, atualizado):
    1. POST /ocorrencia   -> cria o registro (data_hora, status, zona)
    2. Se status == "BLOQUEADA": POST /api/alerta -> vincula uma mensagem
       Ã  ocorrÃªncia criada no passo 1 (usa o id_ocorrencia retornado)

NOTA IMPORTANTE (mudanÃ§a recente no backend):
    A Ocorrencia deixou de referenciar "maquina" diretamente -- agora
    referencia "zona" (uma entidade nova, que por sua vez referencia a
    mÃ¡quina). Por isso o mapa de IDs mudou de MAQUINA_ID_MAP pra
    ZONA_ID_MAP -- precisa do id_zona (nÃ£o mais id_maquina).

    Os prefixos de rota tambÃ©m nÃ£o sÃ£o uniformes no backend dele:
    /api/alerta e /api/zona tÃªm "/api", mas /ocorrencia, /maquina e
    /funcionario nÃ£o tÃªm. Os caminhos abaixo jÃ¡ refletem isso.

MODO TESTE (agora):
    BASE_URL aponta pro webhook.site. Ele aceita qualquer JSON e nÃ£o
    devolve um id_ocorrencia de verdade, entÃ£o o passo 2 (alerta) nÃ£o
    vai encadear corretamente -- Ã© esperado. Serve sÃ³ pra vocÃª e seu
    colega conferirem se o formato do payload estÃ¡ certo.

MODO PRODUÃ‡ÃƒO (depois):
    Troque BASE_URL pela URL real do backend (ex: http://IP:8080).
    Os ids das zonas (ZONA_ID_MAP) nÃ£o ficam mais fixos aqui -- cada
    cÃ¢mera define os seus no prÃ³prio arquivo de config (ex:
    config/camera_1.json), e o script principal sobrescreve
    webhook_client.ZONA_ID_MAP na inicializaÃ§Ã£o.
"""

import threading
import time
import requests

# =========================
# CONFIGURAÃ‡ÃƒO
# =========================

# URL padrÃ£o do tÃºnel informado pelo backend. O script principal pode
# sobrescrever este valor atravÃ©s de "backend_url" no JSON da cÃ¢mera.
#BASE_URL = "https://webhook.site/9652c05a-96ea-4970-a155-0cf991c94ca5"

# --- MODO PRODUÃ‡ÃƒO (quando o backend estiver no ar, troque para isso) ---
BASE_URL = "https://unideographical-nonnocturnally-jarred.ngrok-free.dev"

# Preenchido em runtime pelo script principal, a partir do config da
# cÃ¢mera (ex: config/camera_1.json). Chave = nome da zona no seu
# script (ex: "MAQUINA_1"), valor = id_zona real no banco do backend.
ZONA_ID_MAP = {}

REQUEST_TIMEOUT = 5
VERBOSE = True


def _post(path, payload):
    """POST bloqueante. Sempre chamado de dentro de uma thread."""
    url = f"{BASE_URL.rstrip('/')}{path}"
    try:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        if VERBOSE:
            print(f"[webhook] POST {path} -> status {resp.status_code}")
        if not resp.ok:
            if VERBOSE:
                print(f"[webhook] resposta de erro: {resp.text[:500]}")
            return None
        try:
            return resp.json()
        except ValueError:
            # webhook.site nÃ£o devolve JSON estruturado com id_ocorrencia
            return None
    except requests.exceptions.RequestException as e:
        if VERBOSE:
            print(f"[webhook] ERRO em POST {path}: {e}")
        return None


def _notify_zone_status(zona_nome, status, epis_faltando, pose_info, funcionario):
    """
    Roda dentro da thread: monta e envia a Ocorrencia e, se bloqueada,
    o Alerta vinculado. SÃ³ Ã© chamado quando o status da zona muda.
    """
    id_zona = ZONA_ID_MAP.get(zona_nome)

    if id_zona is None:
        if VERBOSE:
            print(
                f"[webhook] AVISO: '{zona_nome}' sem id_zona em "
                f"ZONA_ID_MAP -- pulei o envio. Preencha o mapa "
                f"quando tiver os IDs do backend (a zona precisa jÃ¡ "
                f"existir lÃ¡, criada via POST /api/zona)."
            )
        return

    data_hora = time.strftime("%Y-%m-%dT%H:%M:%S")

    ocorrencia_payload = {
        "data_hora": data_hora,
        "status": status,
        "zona": {"id_zona": id_zona},
    }

    # Se o rosto foi reconhecido nesta sessÃ£o de presenÃ§a, manda o
    # funcionario real. Se nÃ£o (ninguÃ©m identificado, ou reconhecimento
    # facial ainda nÃ£o ligado), fica de fora -- o backend aceita null.
    if funcionario and funcionario.get("id_funcionario"):
        ocorrencia_payload["funcionario"] = {"id_funcionario": funcionario["id_funcionario"]}

    resultado = _post("/api/ocorrencia", ocorrencia_payload)

    if status == "BLOQUEADA":
        id_ocorrencia = resultado.get("id_ocorrencia") if resultado else None
        if id_ocorrencia is None:
            if VERBOSE:
                print("[webhook] ocorrÃªncia nÃ£o retornou id_ocorrencia -- alerta nÃ£o serÃ¡ enviado")
            return

        mensagem = "EPI(s) faltando: " + ", ".join(epis_faltando) if epis_faltando else "Zona bloqueada"
        if pose_info and pose_info.get("postura_ok") is False:
            mensagem += " | postura inadequada"

        alerta_payload = {
            "mensagem": mensagem,
            # Pela polÃ­tica de severidade do challenge, falta de EPI e
            # postura de risco persistente sÃ£o alertas de severidade ALTA.
            "status": "ALTA",
            "data_hora": data_hora,
            "ocorrencia": {"id_ocorrencia": id_ocorrencia},
        }
        # Nota: rota tem prefixo /api, diferente de /ocorrencia
        _post("/api/alerta", alerta_payload)


def notify_zone_status_async(zona_nome, status, epis_faltando=None, pose_info=None, funcionario=None):
    """
    Ponto de entrada usado pelo script principal. Dispara o fluxo
    Ocorrencia (+ Alerta se bloqueado) em uma thread separada, para
    nÃ£o travar o loop de vÃ­deo.
    """
    t = threading.Thread(
        target=_notify_zone_status,
        args=(zona_nome, status, epis_faltando or [], pose_info or {}, funcionario),
        daemon=True,
    )
    t.start()

