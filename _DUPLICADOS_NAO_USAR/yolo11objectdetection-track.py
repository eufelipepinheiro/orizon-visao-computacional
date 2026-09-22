python yolo11objectdetection-track.py camera_1.jsonimport sys
import json
import cv2
import numpy as np
from ultralytics import YOLO
import cvzone
from pose_check import process_pose, check_sustained_posture
import webhook_client
from webhook_client import notify_zone_status_async, BASE_URL
from zone_loader import load_zones_from_api
import face_id
from esp32_led import Esp32Led

# =========================
# CONFIG DA CÂMERA (por comodo/sala)
# =========================
# Uso: python yolo11objectdetection-track.py config/camera_1.json
if len(sys.argv) < 2:
    print("Uso: python yolo11objectdetection-track.py <caminho_do_config.json>")
    print("Exemplo: python yolo11objectdetection-track.py config/camera_1.json")
    sys.exit(1)

CONFIG_PATH = sys.argv[1]

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

COMODO = config["comodo"]
CAMERA_SOURCE = config["camera_source"]
ESP32_PORT = config.get("esp32_port", "COM6")
ESP32_HABILITADO = config.get("esp32_habilitado", True)

# Opcional no config (se não existir, assume False -- não quebra
# configs antigos que ainda não têm esse campo). Se True, a zona só
# fica OK se o funcionário for reconhecido, além de EPI e postura.
EXIGE_RECONHECIMENTO_FACIAL = config.get("exige_reconhecimento_facial", False)

print(f"=== Iniciando monitoramento: {COMODO} (config: {CONFIG_PATH}) ===")

# Monta o mapa zona -> id_zona (backend mudou: Ocorrencia agora
# referencia Zona, não mais Maquina diretamente) e sobrescreve o mapa
# global usado pelo webhook_client (usado tanto pra enviar ocorrências
# quanto pra buscar zonas da API).
webhook_client.ZONA_ID_MAP = {
    nome: dados.get("id_zona") for nome, dados in config["zonas"].items()
}
webhook_client.DEFAULT_FUNCIONARIO_ID = config.get("funcionario_padrao_id")

if webhook_client.DEFAULT_FUNCIONARIO_ID is None:
    print("[webhook] AVISO: funcionario_padrao_id não configurado; ocorrências sem reconhecimento não serão enviadas")

# =========================
# MODELO
# =========================
model = YOLO("best.pt")
names = model.model.names

# =========================
# CAMERA - DETECTAR RESOLUÇÃO
# =========================
cap = cv2.VideoCapture(CAMERA_SOURCE)

# Pegar resolução real da câmera
camera_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
camera_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

print(f"Câmera resolução detectada: {camera_width}x{camera_height}")

# =========================
# ZONAS - COM AUTO-SCALING
# =========================
def scale_zone(zone_points, sx, sy):
    """Escala os pontos de uma zona."""
    return np.array([
        [int(x * sx), int(y * sy)] for x, y in zone_points
    ], np.int32)

# Resolução de referência do config -- usada tanto pro fallback local
# quanto como default caso a API não informe a dela própria.
ref = config["resolucao_referencia"]
scale_x = camera_width / ref["largura"]
scale_y = camera_height / ref["altura"]

# Fallback local: pontos que já vêm no arquivo de config deste comodo.
# Usado só se a API não responder ou a zona ainda não tiver sido
# calibrada pelo site.
FALLBACK_ZONAS = {}
for nome, dados in config["zonas"].items():
    FALLBACK_ZONAS[nome] = {
        "polygon": scale_zone(dados["polygon_fallback"], scale_x, scale_y),
        "epis_obrigatorios": set(dados["epis_obrigatorios"])
    }

# Tenta buscar as zonas calibradas via site (API). Zonas sem id_zona
# no config, ou que a API não retornar, caem pro fallback acima.
ZONAS = load_zones_from_api(
    camera_width=camera_width,
    camera_height=camera_height,
    zona_id_map=webhook_client.ZONA_ID_MAP,
    api_url=BASE_URL,
    fallback=FALLBACK_ZONAS,
)

for nome, zona in ZONAS.items():
    print(f"{nome} pontos escalados: {zona['polygon'].tolist()}")

# =========================
# RECONHECIMENTO FACIAL (uma vez por sessão de presença)
# =========================
face_id.load_known_faces(BASE_URL)

# =========================
# FUNÇÃO: zona
# =========================
def get_zona(cx, cy):
    for nome, zona in ZONAS.items():
        poly = zona["polygon"]
        if cv2.pointPolygonTest(poly, (cx, cy), False) >= 0:
            return nome
    return None


# =========================
# JANELA
# =========================
count = 0

# Guarda o último status enviado ao webhook por zona, para só disparar
# uma requisição quando o status realmente mudar (OK <-> BLOQUEADA)
last_status_sent = {nome: None for nome in ZONAS.keys()}

cv2.namedWindow(f"RGB - {COMODO}", cv2.WINDOW_NORMAL)
cv2.resizeWindow(f"RGB - {COMODO}", 1280, 720)

# =========================
# HUD CONFIG (IMPORTANTE)
# =========================
# Proporcional à resolução da câmera -- os valores fixos antigos (2.2,
# 3, 60, 120) foram calibrados pra uma câmera de 2560x2048. Numa
# câmera menor (ex: 640x480) isso ficava gigante e cortava o texto.
_hud_scale = camera_width / 1280.0
FONT_SCALE = max(0.6, round(2.2 * _hud_scale, 2))
THICKNESS = max(1, round(3 * _hud_scale))
SPACING = max(22, round(60 * _hud_scale))
Y_BASE = max(30, round(120 * _hud_scale))

# A porta serial é aberta uma vez. O ESP32 começa bloqueado por segurança.
esp32 = Esp32Led(porta=ESP32_PORT, habilitado=ESP32_HABILITADO)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    count += 1
    if count % 3 != 0:
        continue

    # =========================
    # POSE
    # =========================
    frame_original = frame.copy()  # sem desenhos -- usado no reconhecimento facial
    has_human, is_live, posture_ok, pose_status, frame = process_pose(frame)

    # True só se a postura estiver ruim de forma sustentada (não é um
    # movimento rápido e normal do trabalho, tipo abaixar pra pegar algo)
    postura_bloqueio = check_sustained_posture(posture_ok)

    # Só roda reconhecimento facial de verdade na primeira vez que
    # alguém entra em cena; enquanto continuar em cena, reaproveita.
    funcionario_atual = face_id.get_current_identity(frame_original, has_human)

    # =========================
    # DESENHAR ZONAS
    # =========================
    for nome, zona in ZONAS.items():
        cv2.polylines(frame, [zona["polygon"]], True, (255, 255, 255), 2)
        cvzone.putTextRect(
            frame,
            nome,
            tuple(zona["polygon"][0]),
            max(0.4, round(1.5 * _hud_scale, 2)),
            max(1, round(2 * _hud_scale)),
            colorR=(255, 255, 255)
        )

    # =========================
    # BLOQUEIO HUMANO
    # =========================
    if not (has_human and is_live):
        esp32.bloquear()

        cvzone.putTextRect(
            frame,
            'ACESSO NEGADO',
            (10, camera_height // 2),
            max(0.6, round(2.5 * _hud_scale, 2)),
            max(1, round(3 * _hud_scale)),
            colorR=(0, 0, 200)
        )

        cv2.imshow(f"RGB - {COMODO}", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
        continue

    if funcionario_atual:
        cvzone.putTextRect(
            frame,
            f"Func: {funcionario_atual['nome']}",
            (10, 30),
            max(0.4, round(1.5 * _hud_scale, 2)),
            max(1, round(2 * _hud_scale)),
            colorR=(0, 150, 0)
        )
    else:
        cvzone.putTextRect(
            frame,
            "Func: nao identificado",
            (10, 30),
            max(0.4, round(1.5 * _hud_scale, 2)),
            max(1, round(2 * _hud_scale)),
            colorR=(0, 100, 200)
        )

    # =========================
    # YOLO
    # =========================
    results = model.track(frame, persist=True)

    epis_por_zona = {z: set() for z in ZONAS.keys()}

    if results[0].boxes is not None:
        boxes = results[0].boxes.xyxy.int().cpu().tolist()
        class_ids = results[0].boxes.cls.int().cpu().tolist()

        for box, class_id in zip(boxes, class_ids):
            c = names[class_id]
            x1, y1, x2, y2 = box

            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2

            zona = get_zona(cx, cy)

            if zona:
                epis_por_zona[zona].add(c)

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cvzone.putTextRect(
                frame, c, (x1, y1),
                max(0.4, round(1.2 * _hud_scale, 2)),
                max(1, round(2 * _hud_scale))
            )

    # =========================
    # VALIDACAO (HUD MAIOR)
    # =========================
    acesso_liberado = bool(ZONAS)

    for i, (nome, zona) in enumerate(ZONAS.items()):
        obrigatorios = zona["epis_obrigatorios"]
        detectados = epis_por_zona[nome]

        faltando = obrigatorios - detectados

        funcionario_bloqueio = EXIGE_RECONHECIMENTO_FACIAL and not funcionario_atual

        if not faltando and not postura_bloqueio and not funcionario_bloqueio:
            status = "OK"
            cor = (0, 200, 80)
        else:
            status = "BLOQUEADA"
            cor = (0, 0, 200)
            acesso_liberado = False

        msg = f"{nome}: {status}"

        if faltando:
            msg += f" | falta: {', '.join(faltando)}"
        if postura_bloqueio:
            msg += " | postura inadequada (sustentada)"
        if funcionario_bloqueio:
            msg += " | funcionario nao identificado"

        # =========================
        # WEBHOOK: só envia se o status mudou
        # =========================
        if status != last_status_sent[nome]:
            last_status_sent[nome] = status

            notify_zone_status_async(
                zona_nome=nome,
                status=status,
                epis_faltando=list(faltando),
                pose_info={
                    "comodo": COMODO,
                    "humano_detectado": has_human,
                    "is_live": is_live,
                    "postura_ok": posture_ok,
                    "detalhes": pose_status,
                },
                funcionario=funcionario_atual,
            )

        cvzone.putTextRect(
            frame,
            msg,
            (10, Y_BASE + i * SPACING),
            FONT_SCALE,
            THICKNESS,
            colorR=cor
        )

    if acesso_liberado:
        esp32.liberar()
    else:
        esp32.bloquear()

    cv2.imshow(f"RGB - {COMODO}", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

esp32.fechar()
cap.release()
cv2.destroyAllWindows()
