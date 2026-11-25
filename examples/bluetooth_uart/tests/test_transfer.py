"""Testes de transporte e execucao, sem radio nem hardware Pololu."""
import hashlib
import importlib.util
from pathlib import Path
import queue
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

EXAMPLE = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, EXAMPLE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


receiver = load("receiver")
sender = load("send_static")
receiver.time = SimpleNamespace(
    ticks_ms=lambda: int(time.monotonic() * 1000),
    ticks_diff=lambda now, start: now - start,
    sleep_ms=lambda ms: time.sleep(ms / 1000),
)


def frame(code):
    return ("S2P1 %d %s\n" % (len(code), hashlib.sha256(code).hexdigest())).encode() + code


class BufferedUART:
    def __init__(self, data):
        self.data = bytearray(data)
        self.output = bytearray()

    def read(self, count):
        # A UART pode devolver menos bytes do que foi solicitado.
        count = min(count, 3)
        result = bytes(self.data[:count])
        del self.data[:count]
        return result or None

    def write(self, data):
        self.output.extend(data)
        return len(data)


class Endpoint:
    def __init__(self, incoming, outgoing):
        self.incoming = incoming
        self.outgoing = outgoing

    def read(self, count):
        try:
            # Um byte por leitura simula fragmentacao extrema em ambos os lados.
            return self.incoming.get(timeout=0.002)
        except queue.Empty:
            return b""

    def write(self, data):
        for value in data:
            self.outgoing.put(bytes([value]))
        return len(data)


class TransferTests(unittest.TestCase):
    def test_ping(self):
        uart = BufferedUART(b"PING\n")
        stop = Mock()
        receiver.handle_request(uart, stop)
        self.assertEqual(uart.output, b"PONG\n")
        stop.assert_not_called()

    def test_actual_blink_file_end_to_end(self):
        host_in, device_in = queue.Queue(), queue.Queue()
        host = Endpoint(host_in, device_in)
        device = Endpoint(device_in, host_in)
        led, stop = Mock(), Mock()
        robot = SimpleNamespace(YellowLED=lambda: led)
        errors = []

        def serve():
            try:
                receiver.handle_request(device, stop)  # PING
                receiver.handle_request(device, stop)  # codigo
            except Exception as exc:
                errors.append(exc)

        with patch.dict("sys.modules", {"zumo_2040_robot": SimpleNamespace(robot=robot)}), \
                patch.object(time, "sleep_ms", create=True):
            worker = threading.Thread(target=serve, daemon=True)
            worker.start()
            sender.transfer(host, sender.DEFAULT_CODE.read_bytes(), timeout=2)
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(led.on.call_count, 5)
        self.assertEqual(led.off.call_count, 6)
        self.assertEqual(stop.call_count, 2)

    def test_corruption_does_not_execute(self):
        data = bytearray(frame(b"raise Exception('should not execute')\n"))
        data[-2] ^= 1
        uart, stop = BufferedUART(data), Mock()
        with self.assertRaisesRegex(receiver.ProtocolError, "HASH"):
            receiver.handle_request(uart, stop)
        self.assertEqual(uart.output, b"READY\n")
        stop.assert_not_called()

    def test_truncated_program_does_not_execute(self):
        uart, stop = BufferedUART(frame(b"pass\n")[:-1]), Mock()
        with patch.object(receiver, "TRANSFER_TIMEOUT_MS", 20):
            with self.assertRaisesRegex(receiver.ProtocolError, "TIMEOUT"):
                receiver.handle_request(uart, stop)
        self.assertEqual(uart.output, b"READY\n")
        stop.assert_not_called()

    def test_bad_headers(self):
        for header in (b"BAD\n", b"S2P1 nope abc\n", b"x" * 97):
            with self.subTest(header=header):
                with self.assertRaisesRegex(receiver.ProtocolError, "HEADER"):
                    receiver.handle_request(BufferedUART(header), Mock())

    def test_reject_size_before_accepting_body(self):
        for size in (0, -1, 4097):
            with self.subTest(size=size):
                uart = BufferedUART(("S2P1 %d %s\n" % (size, "a" * 64)).encode())
                with self.assertRaisesRegex(receiver.ProtocolError, "SIZE"):
                    receiver.handle_request(uart, Mock())
                self.assertEqual(uart.output, b"")

    def test_invalid_digest_format(self):
        uart = BufferedUART(b"S2P1 5 " + b"z" * 64 + b"\n")
        with self.assertRaisesRegex(receiver.ProtocolError, "HASH_FORMAT"):
            receiver.handle_request(uart, Mock())

    def test_invalid_program(self):
        for code in (b"if :\n", b"\xff\xfe"):
            with self.subTest(code=code):
                uart, stop = BufferedUART(frame(code)), Mock()
                receiver.handle_request(uart, stop)
                self.assertEqual(uart.output, b"READY\nERR SYNTAX\n")
                stop.assert_not_called()

    def test_execution_failure_stops_motors(self):
        uart, stop = BufferedUART(frame(b"raise ValueError('test')\n")), Mock()
        receiver.handle_request(uart, stop)
        self.assertEqual(uart.output, b"READY\nRUNNING\nERR EXEC\n")
        self.assertEqual(stop.call_count, 2)

    def test_next_program_gets_fresh_namespace(self):
        uart = BufferedUART(frame(b"old_value = 42\n") + frame(b"assert 'old_value' not in globals()\n"))
        receiver.handle_request(uart, Mock())
        receiver.handle_request(uart, Mock())
        self.assertEqual(uart.output, b"READY\nRUNNING\nDONE\n" * 2)

    def test_sender_surfaces_remote_error(self):
        with self.assertRaisesRegex(RuntimeError, "ERR HASH"):
            sender.expect(BufferedUART(b"ERR HASH\n"), "RUNNING", timeout=0.1)

    def test_sender_reports_missing_response(self):
        with self.assertRaises(TimeoutError):
            sender.expect(BufferedUART(b""), "PONG", timeout=0.01)


if __name__ == "__main__":
    unittest.main()
