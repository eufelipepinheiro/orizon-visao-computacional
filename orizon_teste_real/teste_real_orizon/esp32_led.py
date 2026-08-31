"""Controle dos LEDs do ESP32 pelo estado calculado no programa Python."""

import time

try:
    import serial
except ImportError:
    serial = None


class Esp32Led:
    def __init__(self, porta="COM6", baudrate=115200, habilitado=True):
        self._ultimo_comando = None
        self._serial = None

        if not habilitado:
            print("[ESP32] Integração desabilitada no config")
            return

        if serial is None:
            print("[ESP32] PySerial ausente. Instale com: python -m pip install pyserial")
            return

        try:
            self._serial = serial.Serial(porta, baudrate, timeout=1)
            time.sleep(2)
            print(f"[ESP32] Conectado em {porta}")
            self.bloquear()
        except serial.SerialException as erro:
            print(f"[ESP32] Não foi possível abrir {porta}: {erro}")

    def _enviar(self, comando):
        if self._serial is None or comando == self._ultimo_comando:
            return

        try:
            self._serial.write(f"{comando}\n".encode("utf-8"))
            self._serial.flush()
            self._ultimo_comando = comando
            print(f"[ESP32] {comando}")
        except serial.SerialException as erro:
            print(f"[ESP32] Erro de comunicação: {erro}")

    def liberar(self):
        self._enviar("LIBERADO")

    def bloquear(self):
        self._enviar("BLOQUEADO")

    def fechar(self):
        if self._serial is not None and self._serial.is_open:
            self._serial.close()

