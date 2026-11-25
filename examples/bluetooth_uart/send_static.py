"""Emissor CPython para Raspberry Pi/Linux ou PC com porta serial Bluetooth."""
import argparse
import hashlib
from pathlib import Path
import sys
import time

MAX_CODE_BYTES = 4096
DEFAULT_CODE = Path(__file__).with_name("static_blink.py")


def expect(port, expected, timeout, report=print):
    deadline = time.monotonic() + timeout
    response = bytearray()
    while time.monotonic() < deadline:
        char = port.read(1)
        if not char:
            continue
        if char == b"\n":
            message = response.decode("ascii", errors="replace").strip()
            if message != expected:
                raise RuntimeError("Esperado %s; recebido %r" % (expected, message))
            if report is not None:
                report("[robo]", message)
            return
        response.extend(char)
        if len(response) > 128:
            raise RuntimeError("Resposta invalida; confira baud rate e ligacao.")
    raise TimeoutError("Sem resposta %s em %.1f s" % (expected, timeout))


def write_all(port, data):
    if port.write(data) != len(data):
        raise RuntimeError("Escrita serial incompleta")


def transfer(port, payload, timeout, report=print):
    # PING percorre ida e volta pelo HC-05 e pela UART do Zumo.
    write_all(port, b"PING\n")
    expect(port, "PONG", timeout, report)
    if payload is None:
        return
    if not 0 < len(payload) <= MAX_CODE_BYTES:
        raise ValueError("O programa deve ter de 1 a 4096 bytes.")
    digest = hashlib.sha256(payload).hexdigest()
    header = "S2P1 %d %s\n" % (len(payload), digest)
    write_all(port, header.encode("ascii"))
    expect(port, "READY", timeout, report)
    write_all(port, payload)
    expect(port, "RUNNING", timeout, report)
    expect(port, "DONE", timeout, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/rfcomm0", help="Porta Bluetooth, ex.: /dev/rfcomm0 ou COM8")
    parser.add_argument("--baud", type=int, default=9600, help="Configuracao local da porta; nao reconfigura o HC-05")
    parser.add_argument("--file", type=Path, default=DEFAULT_CODE, help="Programa MicroPython finito, ate 4096 bytes")
    parser.add_argument("--ping", action="store_true", help="Testa ida e volta sem enviar codigo")
    parser.add_argument("--timeout", type=float, default=30, help="Tempo maximo por resposta, em segundos")
    args = parser.parse_args()
    if args.timeout <= 0 or args.baud <= 0:
        parser.error("--timeout e --baud devem ser positivos")
    try:
        import serial
    except ImportError:
        print("Instale pyserial: python -m pip install pyserial", file=sys.stderr)
        return 1
    try:
        payload = None if args.ping else args.file.read_bytes()
        if payload is not None:
            if not 0 < len(payload) <= MAX_CODE_BYTES:
                raise ValueError("O programa deve ter de 1 a 4096 bytes.")
            payload.decode("utf-8")  # Valida a codificacao antes de conectar.
            print("Enviando %s (%d bytes)" % (args.file, len(payload)))
        with serial.Serial(args.port, args.baud, timeout=0.2,
                           write_timeout=args.timeout, rtscts=False,
                           dsrdtr=False, xonxoff=False) as port:
            transfer(port, payload, args.timeout)
    except (OSError, ValueError, RuntimeError, serial.SerialException) as exc:
        print("Falha:", exc, file=sys.stderr)
        print("Nao houve reenvio automatico. Se perdeu a resposta, o codigo pode ter rodado.", file=sys.stderr)
        print("Confira o robo e reinicie o receptor antes de repetir.", file=sys.stderr)
        return 1
    print("UART confirmada." if args.ping else "Codigo recebido e executado; teste concluido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
