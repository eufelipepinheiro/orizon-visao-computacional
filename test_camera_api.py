import unittest

from camera_api import normalize_cameras


class CameraApiTest(unittest.TestCase):
    def test_lista_direta_com_campos_do_banco(self):
        cameras, warnings = normalize_cameras(
            [{"ID": 7, "ACESSO": "rtsp://exemplo/stream", "NOME": "Fresa", "DESCRICAO": "Teste"}]
        )
        self.assertEqual([], warnings)
        self.assertEqual("7", cameras[0].camera_id)
        self.assertEqual("rtsp://exemplo/stream", cameras[0].acesso)
        self.assertEqual("Fresa", cameras[0].nome)

    def test_content_paginado_e_aliases(self):
        cameras, warnings = normalize_cameras(
            {"content": [{"id_camera": 2, "url_rtsp": "rtsp://teste", "name": "Camera 2"}]}
        )
        self.assertEqual([], warnings)
        self.assertEqual("2", cameras[0].camera_id)

    def test_hateoas(self):
        cameras, warnings = normalize_cameras(
            {"_embedded": {"cameras": [{"id": 3, "acesso": "rtsp://teste/3", "nome": "Camera 3"}]}}
        )
        self.assertEqual([], warnings)
        self.assertEqual("Camera 3", cameras[0].nome)


if __name__ == "__main__":
    unittest.main()
