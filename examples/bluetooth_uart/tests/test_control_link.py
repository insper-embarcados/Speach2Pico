"""Atraso no retorno nao deve bloquear renovacao do movimento."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import unittest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


link_module = load("control_link")
receiver = load("control_receiver")
receiver.time = SimpleNamespace(ticks_diff=lambda a, b: a - b)


class DelayedPort:
    def __init__(self, delay=0.6):
        self.now = 0
        self.delay = delay
        self.motors = Mock()
        self.controller = receiver.Controller(self.motors)
        self.controller.feed(b"HELLO\n", 0)
        self.motors.reset_mock()
        self.replies = []
        self.buffer = bytearray()
        self.writes = []

    def write(self, data):
        self.writes.append(data)
        for response in self.controller.feed(data, round(self.now * 1000)):
            self.replies.append((self.now + self.delay, response))
        return len(data)

    @property
    def in_waiting(self):
        while self.replies and self.replies[0][0] <= self.now:
            self.buffer.extend(self.replies.pop(0)[1])
        return len(self.buffer)

    def read(self, count):
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result


class LinkTests(unittest.TestCase):
    def test_600ms_ack_delay_does_not_stop_heartbeat(self):
        port = DelayedPort()
        link = link_module.ControlLink(port, clock=lambda: port.now)
        for step in range(401):
            port.now = step / 100
            port.controller.tick(round(port.now * 1000))
            link.step(1500, 1500)
            self.assertLessEqual(len(link.pending), link_module.MAX_PENDING)
        self.assertGreater(link.received, 20)
        self.assertGreater(link.stats()["p95_ms"], 500)
        port.motors.off.assert_not_called()

    def test_total_return_loss_is_bounded_and_robot_stops(self):
        port = DelayedPort(delay=100)
        link = link_module.ControlLink(port, clock=lambda: port.now)
        with self.assertRaises(TimeoutError):
            for step in range(201):
                port.now = step / 100
                port.controller.tick(round(port.now * 1000))
                link.step(1500, 1500)
        self.assertEqual(link.sent, link_module.MAX_PENDING)
        self.assertFalse(port.controller.moving)
        self.assertFalse(port.controller.armed)

    def test_stop_bypasses_full_ack_window(self):
        port = DelayedPort(delay=100)
        link = link_module.ControlLink(port, clock=lambda: port.now)
        for step in range(40):
            port.now = step / 100
            link.step(1000, 1000)
        self.assertEqual(len(link.pending), link_module.MAX_PENDING)
        link.step(0, 0)
        self.assertEqual(port.writes[-1], b"STOP\n")
        self.assertFalse(port.controller.moving)

    def test_old_sequence_cannot_restart_motion(self):
        port = DelayedPort()
        self.assertEqual(port.controller.feed(b"M 5 0 0\n", 10), [b"ACK 5 OK\n"])
        self.assertEqual(port.controller.feed(b"M 4 1500 1500\n", 20), [b"ACK 4 STALE\n"])
        self.assertFalse(port.controller.moving)


if __name__ == "__main__":
    unittest.main()
