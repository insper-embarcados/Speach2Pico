"""Receptor MicroPython para Zumo 2040: UART0, TX=GP28, RX=GP29.

Carregue por USB com mpremote run. Recebe e executa programas finitos em RAM.
Uso de bancada: executa codigo com todos os privilegios do MicroPython.
"""
import binascii
import hashlib
import time

BAUDRATE = 115200  # Confirmado no HC-06-20190901 renomeado para POLOLU.
MAX_CODE_BYTES = 4096
TRANSFER_TIMEOUT_MS = 15000


class ProtocolError(Exception):
    pass


def read_exact(uart, count, timeout_ms=None):
    if timeout_ms is None:
        timeout_ms = TRANSFER_TIMEOUT_MS
    data = bytearray()
    start = time.ticks_ms()
    while len(data) < count:
        if time.ticks_diff(time.ticks_ms(), start) >= timeout_ms:
            raise ProtocolError("TIMEOUT")
        chunk = uart.read(count - len(data))
        if chunk:
            data.extend(chunk)
        else:
            time.sleep_ms(2)
    return bytes(data)


def read_header(uart):
    data = bytearray()
    start = time.ticks_ms()
    while len(data) < 96:
        remaining = TRANSFER_TIMEOUT_MS - time.ticks_diff(time.ticks_ms(), start)
        if remaining <= 0:
            raise ProtocolError("TIMEOUT")
        char = read_exact(uart, 1, remaining)
        if char == b"\n":
            return bytes(data).strip()
        data.extend(char)
    raise ProtocolError("HEADER")


def reply(uart, message):
    data = (message + "\n").encode()
    if uart.write(data) != len(data):
        raise ProtocolError("WRITE")


def handle_request(uart, stop_motors):
    header = read_header(uart)
    if header == b"PING":
        reply(uart, "PONG")
        return
    parts = header.split()
    if len(parts) != 3 or parts[0] != b"S2P1":
        raise ProtocolError("HEADER")
    try:
        length = int(parts[1])
    except ValueError:
        raise ProtocolError("HEADER")
    if not 0 < length <= MAX_CODE_BYTES:
        raise ProtocolError("SIZE")
    if len(parts[2]) != 64 or any(c not in b"0123456789abcdef" for c in parts[2]):
        raise ProtocolError("HASH_FORMAT")

    reply(uart, "READY")
    payload = read_exact(uart, length)
    digest = binascii.hexlify(hashlib.sha256(payload).digest())
    if digest != parts[2]:
        raise ProtocolError("HASH")
    try:
        program = compile(payload.decode("utf-8"), "<bluetooth>", "exec")
    except (SyntaxError, UnicodeError):
        reply(uart, "ERR SYNTAX")
        return

    stop_motors()
    reply(uart, "RUNNING")
    try:
        # Namespace separado por envio; isto NAO e um ambiente isolado de seguranca.
        exec(program, {"__name__": "__main__"})
    except Exception as exc:
        print("Erro no programa recebido:", repr(exc))
        reply(uart, "ERR EXEC")
    else:
        reply(uart, "DONE")
    finally:
        stop_motors()


def main():
    from machine import Pin, UART
    from zumo_2040_robot import robot

    motors = robot.Motors()
    motors.off()
    uart = UART(0, baudrate=BAUDRATE, bits=8, parity=None, stop=1,
                tx=Pin(28), rx=Pin(29), rxbuf=8192,
                timeout=0, timeout_char=2)
    print("Bluetooth pronto: UART0 TX=GP28 RX=GP29,", BAUDRATE, "baud")
    print("Aguardando PING ou codigo. Ctrl+C via USB encerra.")
    try:
        while True:
            if uart.any():
                try:
                    handle_request(uart, motors.off)
                except ProtocolError as exc:
                    reply(uart, "ERR " + str(exc))
                    print("Transmissao interrompida:", exc)
                    print("Reinicie o receptor antes de tentar novamente.")
                    break  # Nao interpretar restos de um envio como outro programa.
            else:
                time.sleep_ms(5)
    finally:
        motors.off()
        # Aguarda a ultima resposta sair antes de desativar a UART.
        time.sleep_ms(100)
        uart.deinit()


if __name__ == "__main__":
    main()
