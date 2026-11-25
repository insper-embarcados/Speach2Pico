"""Controle continuo do Zumo: UART0 GP28/GP29, 115200, watchdog local.

Use com control_gui.py. Para receber arquivos Python, use receiver.py.
"""
import time

BAUDRATE = 115200
WATCHDOG_MS = 300
FRAME_TIMEOUT_MS = 200
MAX_SPEED = 3000


class Controller:
    def __init__(self, motors):
        self.motors = motors
        self.armed = False
        self.moving = False
        self.last_move = None
        self.buffer = bytearray()
        self.frame_start = None
        self.discard = False
        self.last_sequence = -1
        self.motors.off()

    def stop(self, disarm=False):
        self.motors.off()
        self.moving = False
        if disarm:
            self.armed = False

    def tick(self, now):
        if self.moving and time.ticks_diff(now, self.last_move) >= WATCHDOG_MS:
            self.stop(disarm=True)
        if self.frame_start is not None and time.ticks_diff(now, self.frame_start) >= FRAME_TIMEOUT_MS:
            self.stop(disarm=True)
            self.buffer = bytearray()
            self.frame_start = None
            self.discard = True

    def handle_line(self, line, now):
        if line == b"HELLO":
            self.stop()
            self.armed = True
            self.last_sequence = -1
            return b"POLOLU_CONTROL_V2\n"
        if line == b"STOP":
            self.stop()
            return b"STOPPED\n"
        fields = line.split()
        sequence = None
        try:
            if len(fields) == 4 and fields[0] == b"M":
                sequence = int(fields[1])
                if sequence < 0:
                    raise ValueError()
                fields = [fields[0], fields[2], fields[3]]
            if len(fields) != 3 or fields[0] != b"M":
                raise ValueError()
            left, right = int(fields[1]), int(fields[2])
            if abs(left) > MAX_SPEED or abs(right) > MAX_SPEED:
                raise ValueError()
        except ValueError:
            self.stop(disarm=True)
            return b"ERR COMMAND\n"
        if not self.armed:
            self.stop()
            return b"ERR RECONNECT\n"
        if sequence is not None and sequence <= self.last_sequence:
            # Pacotes antigos nao renovam o watchdog nem reaplicam direcoes.
            return ("ACK %d STALE\n" % sequence).encode()
        self.motors.set_speeds(left, right)
        self.moving = bool(left or right)
        self.last_move = now
        if sequence is not None:
            self.last_sequence = sequence
            return ("ACK %d OK\n" % sequence).encode()
        return b"OK\n"

    def feed(self, data, now):
        self.tick(now)
        responses = []
        for value in data:
            if self.discard:
                if value == 10:
                    self.discard = False
                    responses.append(b"ERR FRAME\n")
                continue
            if value == 10:
                responses.append(self.handle_line(bytes(self.buffer).strip(), now))
                self.buffer = bytearray()
                self.frame_start = None
            elif len(self.buffer) >= 48:
                self.stop(disarm=True)
                self.buffer = bytearray()
                self.frame_start = None
                self.discard = True
            else:
                if self.frame_start is None:
                    self.frame_start = now
                self.buffer.append(value)
        return responses


def main():
    from machine import Pin, UART
    from zumo_2040_robot import robot

    controller = Controller(robot.Motors())
    uart = UART(0, baudrate=BAUDRATE, bits=8, parity=None, stop=1,
                tx=Pin(28), rx=Pin(29), rxbuf=512, timeout=0, timeout_char=2)
    print("Controle continuo pronto: UART0 GP28/GP29, 115200 baud")
    print("Use control_gui.py. Parada automatica apos 300 ms sem renovar movimento.")
    try:
        while True:
            now = time.ticks_ms()
            controller.tick(now)
            data = uart.read(128)
            if data:
                for response in controller.feed(data, time.ticks_ms()):
                    if uart.write(response) != len(response):
                        raise OSError("Falha ao responder pela UART")
            time.sleep_ms(2)
    finally:
        controller.stop(disarm=True)
        uart.deinit()


if __name__ == "__main__":
    main()
