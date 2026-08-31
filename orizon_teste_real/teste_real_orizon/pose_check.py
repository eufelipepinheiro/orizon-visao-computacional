import cv2
import mediapipe as mp
import numpy as np
import time
from collections import deque

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)

MOVEMENT_THRESHOLD = 0.008
MOVEMENT_WINDOW    = 50
POSTURE_ANGLE_MAX  = 30

# Quanto tempo (em segundos) a postura precisa continuar ruim, sem
# interrupção, antes de considerar isso um bloqueio de verdade.
POSTURE_BLOCK_SECONDS = 3.0

keypoint_history = deque(maxlen=MOVEMENT_WINDOW)
_posture_bad_since = None

def check_liveness(history):
    if len(history) < MOVEMENT_WINDOW:
        return None, "Calibrando..."

    key_indices = [
        mp_pose.PoseLandmark.LEFT_SHOULDER,
        mp_pose.PoseLandmark.RIGHT_SHOULDER,
        mp_pose.PoseLandmark.LEFT_HIP,
        mp_pose.PoseLandmark.RIGHT_HIP,
    ]
    movements = []
    for i in key_indices:
        positions = [frame[i] for frame in history]
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        movements.append(np.std(xs) + np.std(ys))

    avg_movement = np.mean(movements)
    is_live = avg_movement > MOVEMENT_THRESHOLD
    return is_live, f"Movimento: {avg_movement:.4f}"

def check_posture(landmarks):
    lm = landmarks

    def pt(idx):
        l = lm[idx]
        return [l.x, l.y]

    left_shoulder  = pt(mp_pose.PoseLandmark.LEFT_SHOULDER)
    right_shoulder = pt(mp_pose.PoseLandmark.RIGHT_SHOULDER)
    left_hip       = pt(mp_pose.PoseLandmark.LEFT_HIP)
    right_hip      = pt(mp_pose.PoseLandmark.RIGHT_HIP)

    mid_shoulder = np.mean([left_shoulder, right_shoulder], axis=0)
    mid_hip      = np.mean([left_hip, right_hip], axis=0)

    trunk_vec  = mid_shoulder - mid_hip
    vertical   = np.array([0, -1])
    cos_t      = np.dot(trunk_vec, vertical) / (np.linalg.norm(trunk_vec) + 1e-6)
    trunk_tilt = np.degrees(np.arccos(np.clip(cos_t, -1, 1)))

    nose      = pt(mp_pose.PoseLandmark.NOSE)
    head_down = nose[1] - mid_shoulder[1] > 0.05

    posture_ok = trunk_tilt < POSTURE_ANGLE_MAX and not head_down

    issues = []
    if trunk_tilt >= POSTURE_ANGLE_MAX:
        issues.append(f"tronco inclinado {trunk_tilt:.0f}g")
    if head_down:
        issues.append("cabeca baixa")

    status = "Postura OK" if posture_ok else f"Postura ruim: {', '.join(issues)}"
    return posture_ok, status


def check_sustained_posture(posture_ok):
    """
    Retorna True só se a postura estiver ruim de forma CONTÍNUA por
    pelo menos POSTURE_BLOCK_SECONDS. Um mau posicionamento rápido não conta -- só bloqueia
    de verdade se a pessoa mantiver a postura ruim por um tempo.

    posture_ok: True (boa), False (ruim), ou None (ainda não avaliável,
        ex: liveness ainda calibrando).
    """
    global _posture_bad_since

    if posture_ok is None or posture_ok:
        _posture_bad_since = None
        return False

    now = time.time()
    if _posture_bad_since is None:
        _posture_bad_since = now
        return False

    return (now - _posture_bad_since) >= POSTURE_BLOCK_SECONDS

def process_pose(frame):
    rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = pose.process(rgb)

    status = {"humano": "Sem humano", "liveness": "-", "postura": "-"}
    is_live    = None
    posture_ok = None

    if not results.pose_landmarks:
        keypoint_history.clear()
        return False, None, None, status, frame

    status["humano"] = "Detectado"
    lm = results.pose_landmarks.landmark
    keypoint_history.append([(l.x, l.y) for l in lm])

    is_live, live_msg = check_liveness(keypoint_history)
    if is_live is None:
        status["liveness"] = live_msg
    else:
        status["liveness"] = "Humano vivo" if is_live else "Estatico! Manequim ou foto?"

    if is_live:
        posture_ok, posture_msg = check_posture(lm)
        status["postura"] = posture_msg
    else:
        status["postura"] = "-"

    mp.solutions.drawing_utils.draw_landmarks(
        frame,
        results.pose_landmarks,
        mp_pose.POSE_CONNECTIONS,
        mp.solutions.drawing_utils.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
        mp.solutions.drawing_utils.DrawingSpec(color=(0, 200, 255), thickness=2),
    )

    return True, is_live, posture_ok, status, frame