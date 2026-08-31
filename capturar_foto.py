"""
capturar_foto.py

Tira uma foto da câmera indicada e salva como .jpg -- usar essa foto
no calibracao_zonas_web.html pra clicar os pontos das zonas.

Uso:
    python capturar_foto.py 0
    (troque o "0" pelo camera_source para fotografar)
"""

import sys
import cv2

if len(sys.argv) < 2:
    print("Uso: python capturar_foto.py <camera_source>")
    print("Exemplo: python capturar_foto.py 0")
    sys.exit(1)

camera_source = int(sys.argv[1])

cap = cv2.VideoCapture(camera_source)
if not cap.isOpened():
    print(f"Não consegui abrir a câmera {camera_source}")
    sys.exit(1)

print("Pressione ESPAÇO para tirar a foto, ou Q para sair sem salvar.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Não consegui ler o frame da câmera.")
        break

    cv2.imshow(f"Camera {camera_source} - ESPACO para capturar, Q para sair", frame)
    key = cv2.waitKey(1) & 0xFF

    if key == ord(" "):
        nome_arquivo = f"foto_camera_{camera_source}.jpg"
        cv2.imwrite(nome_arquivo, frame)
        h, w = frame.shape[:2]
        print(f"\nFoto salva: {nome_arquivo}  (resolução {w}x{h})")
        print("Use essa foto no calibracao_zonas_web.html.")
        break

    if key == ord("q"):
        print("Cancelado, nenhuma foto salva.")
        break

cap.release()
cv2.destroyAllWindows()
