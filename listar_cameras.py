"""
listar_cameras.py

Utilitário pra descobrir qual número (camera_source) corresponde a
cada câmera conectada no seu PC. Roda uma vez, testa os índices de 0 a
9, e mostra o preview de cada câmera encontrada -- anota o número
que aparece no título da janela.

Uso:
    python listar_cameras.py
"""

import cv2

print("Testando índices de câmera de 0 a 9...\n")

for i in range(10):
    cap = cv2.VideoCapture(i)
    if not cap.isOpened():
        cap.release()
        continue

    ret, frame = cap.read()
    if not ret:
        cap.release()
        continue

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"camera_source={i}  ->  resolução {w}x{h}")

    cv2.imshow(f"camera_source = {i}  (pressione qualquer tecla para fechar)", frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    cap.release()

print("\nAnote o número (camera_source) que abriu a câmera certa em cada janela.")
