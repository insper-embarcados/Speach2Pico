"""Regressao para modulos em 115200 e verificacao antes de renomear."""
import contextlib
import importlib.util
import io
from pathlib import Path
import unittest


class Clock:
    def __init__(self):
        self.now = 0

    def ticks_ms(self):
        return self.now

    def ticks_diff(self, now, start):
        return now - start

    def sleep_ms(self, milliseconds):
        self.now += milliseconds


class HC06:
    """Modulo simulado; init altera o host, nunca a velocidade do modulo."""
    def __init__(self, clock, module_baud, version=b"HC-06-20190901"):
        self.clock = clock
        self.module_baud = module_baud
        self.host_baud = None
        self.version = version
        self.buffer = bytearray()
        self.commands = []
        self.last_tx = None

    def init(self, baudrate, *, tx, rx, bits, parity, stop,
             rxbuf, timeout, timeout_char):
        # Reproduz o contrato observado no firmware real: tx/rx obrigatorios.
        if (tx, rx, bits, parity, stop) != (28, 29, 8, None, 1):
            raise AssertionError("Pinos ou formato UART incorretos")
        self.host_baud = baudrate

    def read(self, count=None):
        if not self.buffer:
            return None
        # Respostas fragmentadas para testar a coleta de bytes.
        size = len(self.buffer) if count is None else min(count, 2)
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def write(self, data):
        if self.clock.now < 5000:
            raise AssertionError("Modulo ainda inicializando")
        if self.last_tx is not None and self.clock.now - self.last_tx < 5000:
            raise AssertionError("Intervalo entre comandos insuficiente")
        self.last_tx = self.clock.now
        self.commands.append((self.host_baud, data))
        if b"\r" in data or b"\n" in data:
            raise AssertionError("Comando com terminador indevido")
        if self.host_baud == self.module_baud:
            answers = {b"AT": b"OK", b"AT+VERSION": self.version,
                       b"AT+NAMEPOLOLU": b"OKsetname"}
            if data not in answers:
                raise AssertionError("Comando inesperado: %r" % data)
            self.buffer.extend(answers[data])
        return len(data)


class RenameTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "rename_hc06.py"
        spec = importlib.util.spec_from_file_location("rename_hc06", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.clock = Clock()
        self.module.time = self.clock

    def configure(self, uart):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.module.configure_name(uart, tx=28, rx=29)

    def test_previously_configured_115200(self):
        uart = HC06(self.clock, 115200)
        self.assertTrue(self.configure(uart))
        self.assertEqual(uart.commands, [(115200, b"AT"),
                                        (115200, b"AT+VERSION"),
                                        (115200, b"AT+NAMEPOLOLU")])
        self.assertEqual(uart.module_baud, 115200)

    def test_fallback_to_9600(self):
        uart = HC06(self.clock, 9600)
        self.assertTrue(self.configure(uart))
        self.assertEqual(uart.commands[:3], [(115200, b"AT")] * 3)
        self.assertEqual(uart.commands[-1], (9600, b"AT+NAMEPOLOLU"))
        self.assertEqual(uart.module_baud, 9600)

    def test_no_response_never_sends_name(self):
        uart = HC06(self.clock, None)
        self.assertFalse(self.configure(uart))
        self.assertEqual(uart.commands, [(baud, b"AT") for baud in self.module.BAUDRATES for _ in range(3)])

    def test_previously_configured_38400(self):
        uart = HC06(self.clock, 38400)
        self.assertTrue(self.configure(uart))
        self.assertEqual(uart.commands[-1], (38400, b"AT+NAMEPOLOLU"))
        self.assertEqual(uart.module_baud, 38400)

    def test_unknown_firmware_never_sends_name(self):
        uart = HC06(self.clock, 115200, version=b"linvorV1.8")
        self.assertFalse(self.configure(uart))
        self.assertEqual([data for _, data in uart.commands], [b"AT", b"AT+VERSION"])


if __name__ == "__main__":
    unittest.main()
