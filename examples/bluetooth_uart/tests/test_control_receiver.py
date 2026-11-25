"""Continuidade de movimento, parser e parada local independente do laptop."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location("control_receiver", Path(__file__).resolve().parents[1] / "control_receiver.py")
receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)
receiver.time = SimpleNamespace(ticks_diff=lambda a, b: a - b)


class ControlReceiverTests(unittest.TestCase):
    def setUp(self):
        self.motors = Mock()
        self.controller = receiver.Controller(self.motors)

    def arm(self):
        self.assertEqual(self.controller.feed(b"HELLO\n", 0), [b"POLOLU_CONTROL_V2\n"])
        self.motors.reset_mock()

    def test_continuous_updates_do_not_stop_motors(self):
        self.arm()
        for now in range(0, 2000, 50):
            self.assertEqual(self.controller.feed(b"M 1500 1500\n", now), [b"OK\n"])
        self.assertEqual(self.motors.set_speeds.call_count, 40)
        self.motors.off.assert_not_called()

    def test_stop_applies_without_waiting_for_motion_to_finish(self):
        self.arm()
        self.controller.feed(b"M 1500 1500\n", 10)
        self.assertEqual(self.controller.feed(b"STOP\n", 11), [b"STOPPED\n"])
        self.motors.off.assert_called_once_with()
        self.assertFalse(self.controller.moving)

    def test_link_loss_stops_and_requires_new_handshake(self):
        self.arm()
        self.controller.feed(b"M 1500 1500\n", 10)
        self.controller.tick(309)
        self.motors.off.assert_not_called()
        self.controller.tick(310)
        self.motors.off.assert_called_once_with()
        self.assertEqual(self.controller.feed(b"M 1500 1500\n", 320), [b"ERR RECONNECT\n"])
        self.assertEqual(self.motors.set_speeds.call_count, 1)

    def test_fragmented_commands(self):
        self.arm()
        self.assertEqual(self.controller.feed(b"M -150", 10), [])
        self.assertEqual(self.controller.feed(b"0 1500\n", 12), [b"OK\n"])
        self.motors.set_speeds.assert_called_once_with(-1500, 1500)

    def test_partial_frame_does_not_keep_motors_running(self):
        self.arm()
        self.controller.feed(b"M 1000 1000\nM ", 10)
        self.controller.tick(210)
        self.assertFalse(self.controller.armed)
        self.motors.off.assert_called_once_with()
        self.assertEqual(self.controller.feed(b"1500 1500\n", 211), [b"ERR FRAME\n"])
        self.assertEqual(self.motors.set_speeds.call_count, 1)

    def test_invalid_or_excessive_commands_stop(self):
        for data in (b"M 3001 0\n", b"M -3001 0\n", b"M invalid 100\n", b"M 1\n", b"x" * 80 + b"\n"):
            with self.subTest(data=data):
                self.controller = receiver.Controller(self.motors)
                self.arm()
                self.controller.feed(b"M 1000 1000\n", 0)
                self.controller.feed(data, 10)
                self.assertFalse(self.controller.moving)
                self.assertFalse(self.controller.armed)

    def test_no_movement_before_handshake(self):
        self.assertEqual(self.controller.feed(b"M 1500 1500\n", 0), [b"ERR RECONNECT\n"])
        self.motors.set_speeds.assert_not_called()

    def test_idle_stop_does_not_disarm_connection(self):
        self.arm()
        self.controller.feed(b"STOP\n", 0)
        self.controller.tick(1000)
        self.assertTrue(self.controller.armed)
        self.assertEqual(self.controller.feed(b"M 500 500\n", 1001), [b"OK\n"])


if __name__ == "__main__":
    unittest.main()
