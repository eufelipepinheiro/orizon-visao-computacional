import os
import tempfile
import numpy as np
import cv2
import requests
import face_recognition

REQUEST_TIMEOUT = 10

# Pasta local de fotos de referência -- funciona SEM depender do
# backend. Coloque uma foto por pessoa, nomeada com o nome dela:
#   known_faces/joao_silva.jpg
#   known_faces/maria_souza.jpg
# Use o cadastrar_rosto.py pra tirar e salvar a foto certinho.
LOCAL_FACES_DIR = "known_faces"

# Quão rígida é a comparação. Menor = mais rígido (menos falsos
# positivos, mais falsos negativos). 0.6 é o default da lib; 0.5 é um
# meio-termo mais seguro pra controle de acesso.
MATCH_TOLERANCE = 0.5

_known_encodings = []
_known_labels = []  # lista de dicts {id_funcionario, nome, matricula}

_session_active = False
_session_identity = None


def load_known_faces(api_url):
    """
    Carrega rostos de referência de DUAS fontes:
      1. Pasta local `known_faces/` -- funciona sempre, sem depender
         de backend nenhum. Ótimo pra testar agora.
      2. Backend (GET /funcionario com foto_url) -- lista oficial,
         quando existir.
    As duas se somam; não é uma ou outra.
    Chamar UMA VEZ, na inicialização do script.
    """
    global _known_encodings, _known_labels
    _known_encodings = []
    _known_labels = []

    # --- 1. pasta local ---
    if os.path.isdir(LOCAL_FACES_DIR):
        arquivos = [
            f for f in os.listdir(LOCAL_FACES_DIR)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        for arquivo in arquivos:
            nome = os.path.splitext(arquivo)[0]
            caminho = os.path.join(LOCAL_FACES_DIR, arquivo)
            try:
                image = face_recognition.load_image_file(caminho)
                encodings = face_recognition.face_encodings(image)
                if not encodings:
                    print(f"[face_id] nenhum rosto detectado em '{arquivo}' -- pulei")
                    continue
                _known_encodings.append(encodings[0])
                _known_labels.append({
                    "id_funcionario": None,
                    "nome": nome,
                    "matricula": None,
                    "origem": "local",
                })
            except Exception as e:
                print(f"[face_id] erro lendo '{arquivo}': {e}")
        print(f"[face_id] {len(arquivos)} foto(s) locais carregadas de '{LOCAL_FACES_DIR}/'")
    else:
        print(f"[face_id] pasta '{LOCAL_FACES_DIR}/' não existe -- nenhum rosto local cadastrado")

    # --- 2. backend ---
    try:
        resp = requests.get(f"{api_url.rstrip('/')}/funcionario", timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        funcionarios = resp.json()
    except requests.exceptions.RequestException as e:
        print(f"[face_id] backend indisponível pra buscar funcionários ({e}) -- seguindo só com o cadastro local")
        print(f"[face_id] total: {len(_known_labels)} pessoa(s) cadastradas pra reconhecimento")
        return

    for f in funcionarios:
        foto_url = f.get("foto_url")
        nome = f.get("nome", "?")

        if not foto_url:
            print(f"[face_id] '{nome}' sem foto cadastrada no backend -- pulei")
            continue

        try:
            img_resp = requests.get(foto_url, timeout=REQUEST_TIMEOUT)
            img_resp.raise_for_status()

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(img_resp.content)
                tmp_path = tmp.name

            image = face_recognition.load_image_file(tmp_path)
            os.remove(tmp_path)

            encodings = face_recognition.face_encodings(image)
            if not encodings:
                print(f"[face_id] nenhum rosto detectado na foto de '{nome}' -- pulei")
                continue

            _known_encodings.append(encodings[0])
            _known_labels.append({
                "id_funcionario": f.get("id_funcionario"),
                "nome": nome,
                "matricula": f.get("matricula"),
                "origem": "backend",
            })

        except Exception as e:
            print(f"[face_id] erro processando foto de '{nome}': {e}")

    print(f"[face_id] total: {len(_known_labels)} pessoa(s) cadastradas pra reconhecimento")


def _identify_once(frame):
    """Roda o reconhecimento de fato. Só deve rodar uma vez por sessão."""
    if not _known_encodings:
        return None

    # cv2.cvtColor (em vez de frame[:, :, ::-1]) garante um array
    # contíguo na memória -- versões novas do dlib exigem isso e dão
    # erro de "incompatible function arguments" se a imagem vier de
    # um slice invertido.
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb_frame)
    if not face_locations:
        return None

    encodings = face_recognition.face_encodings(rgb_frame, face_locations)
    if not encodings:
        return None

    face_encoding = encodings[0]
    distances = face_recognition.face_distance(_known_encodings, face_encoding)
    best_idx = int(np.argmin(distances))

    if distances[best_idx] <= MATCH_TOLERANCE:
        pessoa = _known_labels[best_idx]
        print(f"[face_id] identificado: {pessoa['nome']} (distância {distances[best_idx]:.3f})")
        return pessoa

    print(f"[face_id] rosto em cena, mas não reconhecido (distância mínima {distances[best_idx]:.3f})")
    return None


def get_current_identity(frame, has_human):
    """
    Chamar a cada frame, no loop principal. Só dispara reconhecimento
    de fato na primeira vez que has_human vira True; enquanto continuar
    True, reaproveita o resultado. Quando has_human vira False, limpa
    a sessão (a próxima pessoa dispara um novo reconhecimento).

    Retorna: dict {id_funcionario, nome, matricula} ou None
    (ninguém em cena, ou rosto não reconhecido).
    """
    global _session_active, _session_identity

    if not has_human:
        _session_active = False
        _session_identity = None
        return None

    if not _session_active:
        _session_active = True
        _session_identity = _identify_once(frame)

    return _session_identity
