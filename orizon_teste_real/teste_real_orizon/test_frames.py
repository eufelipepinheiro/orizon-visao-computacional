import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from frames_api import FramePublisher, make_server
import webhook_frames as webhook


class Tests(unittest.TestCase):
    def test_real_jpeg(self):
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            frame = np.zeros((120, 160, 3), dtype=np.uint8)
            cv2.rectangle(frame, (20, 20), (80, 90), (0, 255, 0), 3)
            publisher = FramePublisher(13, tmp)
            self.assertTrue(publisher.publish(frame))
            result = cv2.imread(str(Path(tmp, "13.jpg")))
            self.assertEqual(result.shape, frame.shape)
            self.assertGreater(int(result[20, 40, 1]), 180)

    def test_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = make_server(port=0, directory=tmp, token="teste", origin="http://localhost:3000")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def get(path, token="teste"):
                req = Request(f"http://127.0.0.1:{server.server_port}" + path,
                              headers={"Authorization": "Bearer " + token,
                                       "Origin": "http://localhost:3000"})
                try:
                    return urlopen(req, timeout=2)
                except HTTPError as error:
                    return error
            try:
                self.assertEqual(get("/api/cameras/9/frame", "errado").code, 401)
                self.assertEqual(get("/api/cameras/9/frame").code, 503)
                self.assertEqual(get("/api/cameras/../frame").code, 404)
                jpeg = b"\xff\xd8TESTE\xff\xd9"
                Path(tmp, "9.jpg").write_bytes(jpeg)
                response = get("/api/cameras/9/frame?t=1")
                self.assertEqual(response.code, 200)
                self.assertEqual(response.read(), jpeg)
                self.assertEqual(response.headers["Content-Type"], "image/jpeg")
                self.assertIn("no-store", response.headers["Cache-Control"])
                self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://localhost:3000")
                self.assertEqual(get("/api/cameras/13/frame").code, 503)
                os.utime(Path(tmp, "9.jpg"), (time.time()-10, time.time()-10))
                self.assertEqual(get("/api/cameras/9/frame").code, 503)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_publish_throttle(self):
        fake_cv2 = Mock(IMWRITE_JPEG_QUALITY=1)
        fake_cv2.imencode.return_value = (True, Mock(tobytes=lambda: b"JPEG"))
        with tempfile.TemporaryDirectory() as tmp, patch.dict("sys.modules", {"cv2": fake_cv2}):
            publisher = FramePublisher(9, tmp)
            self.assertTrue(publisher.publish(object()))
            self.assertFalse(publisher.publish(object()))
            publisher.last -= 2
            self.assertTrue(publisher.publish(object()))
            self.assertEqual(Path(tmp, "9.jpg").read_bytes(), b"JPEG")
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)

    def test_employee(self):
        webhook.configure(base_url="http://backend.invalid", camera_id=9, funcionario_padrao_id=1)
        webhook.ZONA_ID_MAP = {"MAQUINA_1": 1}
        self.assertEqual(webhook._headers()["X-Camera-Id"], "9")
        with patch.object(webhook, "_post", return_value={"id_ocorrencia": 5}) as post:
            webhook._notify_zone_status("MAQUINA_1", "OK", [], {}, None)
            self.assertEqual(post.call_args.args[1]["funcionario"], {"id_funcionario": 1})
            webhook._notify_zone_status("MAQUINA_1", "OK", [], {}, {"id_funcionario": 7})
            self.assertEqual(post.call_args.args[1]["funcionario"], {"id_funcionario": 7})
            post.reset_mock()
            webhook._notify_zone_status("MAQUINA_1", "BLOQUEADA", ["epi_capacete"], {}, None)
            self.assertEqual(post.call_count, 2)
            self.assertEqual(post.call_args.args[1]["ocorrencia"], {"id_ocorrencia": 5})

    def test_network_requires_token(self):
        with self.assertRaises(ValueError):
            make_server("0.0.0.0", 0)


if __name__ == "__main__":
    unittest.main()
