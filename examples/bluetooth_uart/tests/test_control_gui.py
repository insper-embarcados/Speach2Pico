"""Movimentos finitos e falhas do controle, sem janela ou radio."""
import importlib.util
from pathlib import Path
import queue
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

BASE = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, BASE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


with patch.dict("sys.modules", {"send_static": load("send_static"), "control_link": load("control_link")}):
    gui = load("control_gui")


class FakeEvent:
    def __init__(self, cancel=False):
        self.now = 0
        self.closed = False
        self.cancel = cancel

    def is_set(self):
        return self.closed

    def set(self):
        self.closed = True

    def wait(self, duration):
        self.now += duration
        if self.cancel:
            self.closed = True
        return self.closed


class ControlTests(unittest.TestCase):
    def test_worker_and_receiver_exchange_continuous_commands(self):
        receiver = load("control_receiver")
        receiver.time = SimpleNamespace(ticks_diff=lambda a, b: a - b)
        motors = Mock()
        controller = receiver.Controller(motors)
        intent, closing, events = gui.MotionIntent(), threading.Event(), queue.Queue()
        intent.hold("forward", 1500)

        class Port:
            def __init__(self):
                self.buffer = bytearray()
                self.moves = 0
                self.closed = False

            def write(self, data):
                for reply in controller.feed(data, self.moves * 50):
                    self.buffer.extend(reply)
                if data.startswith(b"M "):
                    self.moves += 1
                    intent.hold("forward", 1500)
                    if self.moves == 3:
                        closing.set()
                return len(data)

            @property
            def in_waiting(self):
                return len(self.buffer)

            def read(self, count):
                result = bytes(self.buffer[:count])
                del self.buffer[:count]
                return result

            def close(self):
                self.closed = True

        port = Port()
        gui.connection_worker("test", intent, closing, events, serial_factory=lambda *a, **k: port)
        self.assertTrue(port.closed)
        self.assertEqual([call[0] for call in motors.method_calls],
                         ["off", "off", "set_speeds", "set_speeds", "set_speeds", "off"])

    def test_direction_commands(self):
        for direction, expected in {"forward": b"M 1500 1500\n", "backward": b"M -1500 -1500\n",
                                    "left": b"M -1500 1500\n", "right": b"M 1500 -1500\n"}.items():
            self.assertEqual(gui.motion_command(direction, 1500), expected)
        self.assertEqual(gui.motion_command("forward", 9000), b"M 3000 3000\n")

    def test_intent_expires_without_ui_refresh(self):
        intent = gui.MotionIntent()
        with patch.object(gui.time, "monotonic", return_value=10):
            intent.hold("forward", 1500)
            self.assertEqual(intent.current(), ("forward", 1500))
        with patch.object(gui.time, "monotonic", return_value=11):
            self.assertIsNone(intent.current())

    def test_release_discards_motion(self):
        intent = gui.MotionIntent()
        intent.hold("forward", 1500)
        intent.hold("left", 500)
        self.assertEqual(intent.current(), ("left", 500))
        intent.stop()
        self.assertIsNone(intent.current())

    def test_failure_retries_then_expires_after_five_seconds(self):
        intent, events = gui.MotionIntent(), queue.Queue()
        intent.hold("forward", 1500)
        closing = FakeEvent()
        ports = []
        def factory(*args, **kwargs):
            port = Mock()
            port.write.side_effect = len
            ports.append(port)
            return port
        with patch.object(gui, "exchange"), patch.object(gui, "ControlLink") as link:
            link.return_value.step.side_effect = TimeoutError("no ACK")
            gui.connection_worker("test", intent, closing, events, serial_factory=factory,
                                  clock=lambda: closing.now)
        self.assertEqual(closing.now, 5)
        self.assertEqual(len(ports), 5)
        for port in ports:
            port.close.assert_called_once_with()
        self.assertIsNone(intent.current())
        kinds = [events.get()[0] for _ in range(events.qsize())]
        self.assertEqual(kinds.count("reconnecting"), 5)
        self.assertEqual(kinds[-2:], ["error", "disconnected"])

    def test_successful_retry_does_not_restore_old_direction(self):
        intent, events, closing = gui.MotionIntent(), queue.Queue(), FakeEvent()
        intent.hold("forward", 1500)
        port = Mock()
        port.write.side_effect = len
        factory = Mock(side_effect=[OSError("radio offline"), port])
        with patch.object(gui, "exchange"), patch.object(gui, "ControlLink") as link:
            link.return_value.step.side_effect = lambda *args: closing.set()
            gui.connection_worker("test", intent, closing, events, serial_factory=factory,
                                  clock=lambda: closing.now)
            link.return_value.step.assert_called_once_with(0, 0)
        self.assertEqual(factory.call_count, 2)
        self.assertEqual(closing.now, 1.005)
        port.close.assert_called_once()

    def test_manual_disconnect_cancels_retry(self):
        intent, events, closing = gui.MotionIntent(), queue.Queue(), FakeEvent(cancel=True)
        factory = Mock(side_effect=OSError("offline"))
        gui.connection_worker("test", intent, closing, events, serial_factory=factory,
                              clock=lambda: closing.now)
        self.assertEqual(factory.call_count, 1)
        kinds = [events.get()[0] for _ in range(events.qsize())]
        self.assertNotIn("error", kinds)
        self.assertEqual(kinds[-1], "disconnected")

    def test_disconnect_sends_stop(self):
        intent, closing, events = gui.MotionIntent(), threading.Event(), queue.Queue()
        port = Mock()
        port.write.side_effect = len
        with patch.object(gui, "exchange"), patch.object(gui, "ControlLink") as link:
            link.return_value.step.side_effect = lambda *args: closing.set()
            gui.connection_worker("test", intent, closing, events, serial_factory=lambda *a, **k: port)
        port.write.assert_called_with(b"STOP\n")
        port.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
