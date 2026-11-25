"""Bluetooth Classic RFCOMM, compatible with examples/bluetooth_uart/receiver.py.

One owner, one socket, no automatic replay. A PONG confirms the entire UART path.
The legacy receiver cannot answer heartbeats or STOP while executing Python.
"""
import hashlib
import socket
import threading
import time


class RobotLink:
    def __init__(self, address="00:23:04:00:33:75", channel=1, socket_factory=None):
        self.address, self.channel = address, channel
        self.factory = socket_factory or self._socket
        self.sock = None
        self.lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.halt = threading.Event()
        self.thread = None
        self.state = dict(connected=False, phase="disconnected", address=address,
                          name="POLOLU", message="Procurando o Pololu…", attempts=0,
                          last_seen=None, latency_ms=None, uncertain=False)

    @staticmethod
    def _socket():
        if not hasattr(socket, "AF_BLUETOOTH"):
            raise RuntimeError("Bluetooth Classic requer Linux com BlueZ.")
        return socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)

    def update(self, **kwargs):
        with self.state_lock:
            self.state.update(kwargs)

    def snapshot(self):
        with self.state_lock:
            return dict(self.state)

    def _close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def _expect(self, expected, timeout=2):
        deadline = time.monotonic() + timeout
        data = bytearray()
        while time.monotonic() < deadline and not self.halt.is_set():
            self.sock.settimeout(min(0.5, max(0.01, deadline - time.monotonic())))
            try:
                char = self.sock.recv(1)
            except socket.timeout:
                continue
            if not char:
                raise ConnectionError("O Pololu fechou a conexão.")
            if char == b"\n":
                line = data.decode("ascii", "replace").strip()
                if line != expected:
                    raise RuntimeError(f"Receptor: {line}; esperado {expected}.")
                self.update(last_seen=time.time())
                return
            data.extend(char)
            if len(data) > 128:
                raise RuntimeError("Resposta inválida do receptor.")
        raise TimeoutError(f"Sem resposta {expected} do receptor.")

    def _ping(self):
        start = time.monotonic()
        self.sock.settimeout(2)
        self.sock.sendall(b"PING\n")
        self._expect("PONG")
        self.update(latency_ms=round((time.monotonic() - start) * 1000))

    def start(self):
        self.thread = threading.Thread(target=self._loop, daemon=True, name="pololu-link")
        self.thread.start()

    def _loop(self):
        while not self.halt.is_set():
            started = time.monotonic()
            if self.lock.acquire(blocking=False):
                try:
                    if self.sock is None:
                        state = self.snapshot()
                        self.update(connected=False, phase="connecting", attempts=state["attempts"] + 1,
                                    message="Reconectando ao Pololu…")
                        self.sock = self.factory()
                        self.sock.settimeout(3)
                        self.sock.connect((self.address, self.channel))
                    self._ping()
                    self.update(connected=True, phase="connected", message="Pololu conectado e respondendo")
                except Exception as exc:
                    self._close()
                    self.update(connected=False, phase="disconnected", message=str(exc)[:240])
                finally:
                    self.lock.release()
            # A scheduler tick each second; a slow OS connect is never overlapped.
            self.halt.wait(max(0.05, 1 - (time.monotonic() - started)))

    def execute(self, code, on_running=lambda: None):
        payload = code.encode("utf-8")
        if not 0 < len(payload) <= 4096:
            raise ValueError("O receptor aceita programas de até 4096 bytes.")
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("Bluetooth ocupado. Tente novamente em um instante.")
        transmitted = False
        try:
            if not self.sock or not self.snapshot()["connected"]:
                raise ConnectionError("Aguarde o Pololu conectar antes de decolar.")
            if self.snapshot()["uncertain"]:
                raise RuntimeError("Confira o robô e reconheça a execução incerta antes de repetir.")
            self.update(phase="transferring", message="Enviando o programa…")
            self._ping()
            self.sock.settimeout(5)
            self.sock.sendall(f"S2P1 {len(payload)} {hashlib.sha256(payload).hexdigest()}\n".encode())
            self._expect("READY", 5)
            # A lost ACK can mean the program already ran. Never retry this payload.
            transmitted = True
            self.sock.settimeout(10)
            self.sock.sendall(payload)
            self._expect("RUNNING", 10)
            self.update(phase="running", message="Executando · receptor ocupado, sem heartbeat")
            on_running()
            self._expect("DONE", 120)
            self.update(phase="connected", message="Missão concluída pelo Pololu")
        except Exception as exc:
            self._close()
            self.update(connected=False, phase="disconnected", uncertain=transmitted or self.snapshot()["uncertain"],
                        message=("Execução incerta; confira o robô. " if transmitted else "") + str(exc)[:200])
            raise
        finally:
            self.lock.release()

    def acknowledge(self):
        self.update(uncertain=False)

    def close(self):
        self.halt.set()
        self._close()
        if self.thread:
            self.thread.join(timeout=4)
