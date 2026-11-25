"""Transporte de controle: envio periodico, ACKs numerados e janela limitada."""
import time

INTERVAL = 0.05
MAX_PENDING = 8
ACK_TIMEOUT = 1.0


class ControlLink:
    def __init__(self, port, clock=time.monotonic):
        self.port, self.clock = port, clock
        self.pending = {}
        self.sequence = 0
        self.buffer = bytearray()
        self.last_send = -100
        self.last_ack = clock()
        self.sent = 0
        self.received = 0
        self.superseded = 0
        self.latencies = []
        self.last_motion = None

    def write(self, data):
        if self.port.write(data) != len(data):
            raise OSError("Escrita Bluetooth incompleta")

    def consume(self):
        # Limite por iteracao: uma entrada ruidosa nao impede o watchdog do host.
        size = min(2048, self.port.in_waiting)
        if size:
            self.buffer.extend(self.port.read(size))
        if len(self.buffer) > 4096:
            raise RuntimeError("Resposta excessiva ou sem terminador")
        while b"\n" in self.buffer:
            line, _, rest = self.buffer.partition(b"\n")
            self.buffer = bytearray(rest)
            fields = bytes(line).strip().split()
            if fields == [b"STOPPED"]:
                continue
            if fields and fields[0] == b"ERR":
                raise RuntimeError("Receptor: " + bytes(line).decode("ascii", "replace"))
            if len(fields) != 3 or fields[0] != b"ACK" or fields[2] != b"OK":
                raise RuntimeError("Resposta inesperada: %r" % bytes(line))
            try:
                seq = int(fields[1])
            except ValueError:
                raise RuntimeError("Numero de confirmacao invalido")
            if seq not in self.pending:
                # ACK duplicado/atrasado nao serve como sinal de vida novo.
                continue
            now = self.clock()
            self.latencies.append((now - self.pending[seq]) * 1000)
            self.latencies = self.latencies[-1000:]
            self.received += 1
            self.last_ack = now
            # O fluxo RFCOMM e ordenado: ACK mais novo supera os anteriores.
            older = [key for key in self.pending if key < seq]
            self.superseded += len(older)
            for key in older + [seq]:
                del self.pending[key]

    def step(self, left, right):
        self.consume()
        now = self.clock()
        if self.pending and now - self.last_ack >= ACK_TIMEOUT:
            raise TimeoutError("Sem confirmacoes recentes por 1 s; reconexao necessaria")
        motion = (left, right)
        # STOP nao fica preso atras da janela de ACKs; motor tem watchdog proprio.
        if motion == (0, 0) and self.last_motion not in (None, (0, 0)):
            self.write(b"STOP\n")
            self.last_motion = motion
        if now - self.last_send < INTERVAL or len(self.pending) >= MAX_PENDING:
            return
        seq = self.sequence
        self.write(("M %d %d %d\n" % (seq, left, right)).encode("ascii"))
        self.pending[seq] = now
        self.sequence += 1
        self.sent += 1
        self.last_send = now
        self.last_motion = motion

    def stats(self):
        values = sorted(self.latencies)
        return {"sent": self.sent, "acknowledged": self.received,
                "superseded": self.superseded, "pending": len(self.pending),
                "median_ms": round(values[len(values)//2], 1) if values else None,
                "p95_ms": round(values[min(len(values)-1, int(len(values)*0.95))], 1) if values else None,
                "max_ms": round(max(values), 1) if values else None}
