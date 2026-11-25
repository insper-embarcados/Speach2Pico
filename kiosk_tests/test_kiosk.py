import socket
import subprocess
import threading
import time
import unittest
from unittest.mock import Mock

from fastapi.testclient import TestClient

from kiosk_app.ai import validate_code
from kiosk_app.bluetooth import RobotLink
from kiosk_app.server import Controller, create_app, DEMO_CODE
from kiosk_app.wifi import Wifi, split_fields


def wait_for(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError("Condition did not become true")


class FakeSocket:
    def __init__(self, reply=b"", fail_payload=False):
        self.reply = bytearray(reply)
        self.writes = []
        self.closed = False
        self.fail_payload = fail_payload

    def settimeout(self, timeout):
        pass

    def connect(self, address):
        self.address = address

    def recv(self, count):
        if not self.reply:
            return b""
        value, self.reply = self.reply[:count], self.reply[count:]
        return bytes(value)

    def sendall(self, payload):
        self.writes.append(payload)
        if self.fail_payload and payload == DEMO_CODE.encode():
            raise OSError("lost")

    def close(self):
        self.closed = True


class TransportTests(unittest.TestCase):
    def link(self, socket):
        link = RobotLink(socket_factory=lambda: socket)
        link.sock = socket
        link.update(connected=True)
        return link

    def test_click_transfers_exact_code_with_digest_and_completion(self):
        import hashlib
        sock = FakeSocket(b"PONG\nREADY\nRUNNING\nDONE\n")
        link = self.link(sock)
        running = Mock()
        link.execute(DEMO_CODE, running)
        self.assertEqual(sock.writes[0], b"PING\n")
        self.assertIn(hashlib.sha256(DEMO_CODE.encode()).hexdigest().encode(), sock.writes[1])
        self.assertEqual(sock.writes[2], DEMO_CODE.encode())
        running.assert_called_once()
        self.assertFalse(link.snapshot()["uncertain"])

    def test_lost_ack_never_replays_program_and_latches_uncertainty(self):
        sock = FakeSocket(b"PONG\nREADY\n", fail_payload=True)
        link = self.link(sock)
        with self.assertRaises(OSError):
            link.execute(DEMO_CODE)
        self.assertEqual(sock.writes.count(DEMO_CODE.encode()), 1)
        self.assertFalse(link.snapshot()["connected"])
        self.assertTrue(link.snapshot()["uncertain"])
        link.sock = FakeSocket()
        link.update(connected=True)
        with self.assertRaisesRegex(RuntimeError, "incerta"):
            link.execute(DEMO_CODE)
        self.assertTrue(link.snapshot()["uncertain"])

    def test_non_pong_cannot_report_connected(self):
        sock = FakeSocket(b"POLOLU_CONTROL_V2\n")
        link = RobotLink(socket_factory=lambda: sock)
        link.start()
        wait_for(lambda: sock.closed)
        self.assertFalse(link.snapshot()["connected"])
        link.close()

    def test_reconnect_ticks_without_replaying(self):
        attempts = []
        def fail():
            attempts.append(time.monotonic())
            raise OSError("unreachable")
        link = RobotLink(socket_factory=fail)
        link.start()
        wait_for(lambda: len(attempts) >= 3, 3.5)
        link.close()
        self.assertGreaterEqual(attempts[1] - attempts[0], .9)
        self.assertLess(attempts[1] - attempts[0], 1.3)

    def test_no_heartbeat_or_second_execution_during_running(self):
        link = self.link(FakeSocket())
        link.lock.acquire()
        with self.assertRaisesRegex(RuntimeError, "ocupado"):
            link.execute(DEMO_CODE)
        self.assertEqual(link.sock.writes, [])
        link.lock.release()


class WifiTests(unittest.TestCase):
    def test_escaped_ssid_and_password_never_in_argv(self):
        self.assertEqual(split_fields(r"*:Lab\:rede:90:WPA2"), ["*", "Lab:rede", "90", "WPA2"])
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
        Wifi(runner).connect("Lab:rede", "private password")
        args, kwargs = runner.call_args
        self.assertNotIn("private password", args[0])
        self.assertEqual(kwargs["input"], "private password\n")
        self.assertNotIn("shell", kwargs)

    def test_secret_not_in_error_and_newline_rejected(self):
        wifi = Wifi(Mock(return_value=subprocess.CompletedProcess([], 1, "secret", "secret")))
        with self.assertRaises(RuntimeError) as caught:
            wifi.connect("lab", "secret")
        self.assertNotIn("secret", str(caught.exception))
        with self.assertRaises(ValueError):
            wifi.connect("lab", "password\nother")

    def test_scan_keeps_active_duplicate_and_internet_separate(self):
        runner = Mock(side_effect=[subprocess.CompletedProcess([], 0, "*:Lab:40:WPA2\n:Lab:90:WPA2\n:Guest:70:--\n", ""), subprocess.CompletedProcess([], 0, "limited\n", "")])
        state = Wifi(runner).snapshot()
        self.assertTrue(state["networks"][0]["connected"])
        self.assertEqual(state["networks"][0]["signal"], 40)
        self.assertEqual(state["internet"], "limited")


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.link = Mock()
        self.link.snapshot.return_value = dict(connected=True, uncertain=False)
        self.ai = Mock()
        self.ai.generate.return_value = DEMO_CODE
        self.ctl = Controller(link=self.link, ai=self.ai, recorder=Mock(), wifi=Mock())
        self.client = TestClient(create_app(self.ctl))
        self.headers = {"X-Kiosk-Request": "1"}

    def post(self, path, body=None):
        import uuid
        data = dict(body or {})
        if path == 'execute':
            data.setdefault('execution_id', uuid.uuid4().hex)
        return self.client.post('/api/' + path, json=data, headers=self.headers)

    def test_generation_does_not_deploy_requires_matching_mission_and_click(self):
        self.assertEqual(self.post("generate", {"text": "pisque"}).status_code, 200)
        wait_for(lambda: self.ctl.state["phase"] == "ready")
        self.link.execute.assert_not_called()
        self.assertEqual(self.post("execute", {"mission_id": "old"}).status_code, 409)
        self.link.execute.assert_not_called()
        self.assertEqual(self.post("execute", {"mission_id": self.ctl.state["mission_id"]}).status_code, 200)
        wait_for(lambda: self.ctl.state["phase"] == "done")
        self.link.execute.assert_called_once()

    def test_double_click_is_blocked_and_does_not_restart(self):
        entered, finish = threading.Event(), threading.Event()
        def run(*args):
            entered.set()
            finish.wait(2)
        self.link.execute.side_effect = run
        self.ctl.state.update(code=DEMO_CODE, mission_id="test", phase="ready")
        self.post("execute", {"mission_id": "test"})
        entered.wait(1)
        self.assertEqual(self.post("execute", {"mission_id": "test"}).status_code, 409)
        self.assertEqual(self.post("new").status_code, 409)
        finish.set()
        wait_for(lambda: self.ctl.state["phase"] == "done")
        self.link.execute.assert_called_once()

    def test_same_execution_request_is_idempotent_even_after_done(self):
        self.ctl.state.update(code=DEMO_CODE, mission_id="test", phase="ready")
        body = {"mission_id": "test", "execution_id": "same-request-123"}
        self.post("execute", body)
        wait_for(lambda: self.ctl.state["phase"] == "done")
        self.assertEqual(self.post("execute", body).status_code, 200)
        self.link.execute.assert_called_once()

    def test_voice_finishes_then_generates_without_ever_deploying(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'voice.wav'
            path.write_bytes(b'fake')
            self.ctl.recorder.finish.return_value = path
            self.ai.transcribe.return_value = "pisque cinco vezes"
            self.assertEqual(self.post('record/start').status_code, 200)
            self.assertEqual(self.post('record/finish').status_code, 200)
            wait_for(lambda: self.ctl.state['phase'] == 'ready')
            self.ai.generate.assert_called_once_with('pisque cinco vezes', None)
            self.link.execute.assert_not_called()
            wait_for(lambda: not path.exists())

    def test_voice_failure_deletes_audio_and_leaves_error_state(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'voice.wav'
            path.write_bytes(b'fake')
            self.ctl.recorder.finish.return_value = path
            self.ai.transcribe.side_effect = ValueError('sem fala')
            self.post('record/start')
            self.post('record/finish')
            wait_for(lambda: self.ctl.state['phase'] == 'error')
            self.assertFalse(path.exists())
            self.ai.generate.assert_not_called()

    def test_generation_failure_never_exposes_old_code_for_execution(self):
        self.ctl.state.update(code=DEMO_CODE, mission_id="old", phase="ready")
        self.ai.generate.side_effect = ValueError("falha da API")
        self.post("generate", {"text": "modifique", "modify": True})
        wait_for(lambda: self.ctl.state["phase"] == "error")
        self.assertEqual(self.ctl.state["code"], "")
        self.assertIsNone(self.ctl.state["mission_id"])
        self.link.execute.assert_not_called()
        self.ai.generate.side_effect = None
        self.post("generate", {"text": "tente de novo", "modify": True})
        wait_for(lambda: self.ctl.state["phase"] == "ready")
        self.ai.generate.assert_called_with("tente de novo", DEMO_CODE)

    def test_mutations_require_same_origin_and_custom_header(self):
        self.assertEqual(self.client.post('/api/new').status_code, 403)
        response = self.client.post('/api/new', headers={**self.headers, "Origin": "https://evil.example"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/api/status', headers={"Host": "evil.example"}).status_code, 400)

    def test_offline_and_uncertain_robot_cannot_execute(self):
        self.ctl.state.update(code=DEMO_CODE, mission_id="test", phase="ready")
        for status in ({"connected": False, "uncertain": False}, {"connected": True, "uncertain": True}):
            self.link.snapshot.return_value = status
            self.assertEqual(self.post("execute", {"mission_id": "test"}).status_code, 409)
        self.link.execute.assert_not_called()

    def test_bad_model_code_never_becomes_ready(self):
        self.ai.generate.return_value = "import os\nos.remove('main.py')"
        self.post("generate", {"text": "bad"})
        wait_for(lambda: self.ctl.state["phase"] == "error")
        self.link.execute.assert_not_called()

    def test_compile_limit_and_finite_program_guard(self):
        self.assertEqual(validate_code(DEMO_CODE), DEMO_CODE)
        for code in ("while True:\n pass", "x='" + "a" * 4096 + "'", "x = getattr(time, 'sleep')"):
            with self.assertRaises(ValueError):
                validate_code(code)


if __name__ == "__main__":
    unittest.main()
