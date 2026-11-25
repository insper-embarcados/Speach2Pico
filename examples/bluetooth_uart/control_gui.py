"""Controle grafico continuo; use com control_receiver.py no Zumo."""
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from send_static import expect, write_all
from control_link import ControlLink

UPDATE_SECONDS = 0.05
LEASE_SECONDS = 0.2
DIRECTIONS = {
    "forward": (1, 1), "backward": (-1, -1),
    "left": (-1, 1), "right": (1, -1),
}


def motion_command(direction, speed):
    left, right = DIRECTIONS[direction]
    speed = max(0, min(3000, int(speed)))
    return ("M %d %d\n" % (left * speed, right * speed)).encode("ascii")


def exchange(port, command, expected, timeout=0.5):
    write_all(port, command)
    expect(port, expected, timeout, report=None)


class MotionIntent:
    """Apenas a direcao atual: sem fila de movimentos antigos."""
    def __init__(self):
        self.lock = threading.Lock()
        self.request = None

    def hold(self, direction, speed):
        with self.lock:
            self.request = (direction, speed, time.monotonic() + LEASE_SECONDS)

    def stop(self):
        with self.lock:
            self.request = None

    def current(self):
        with self.lock:
            if self.request and time.monotonic() < self.request[2]:
                return self.request[:2]
            return None


RETRY_INTERVAL = 1.0
RECONNECT_WINDOW = 5.0


def close_port(port):
    if port is None:
        return
    try:
        write_all(port, b"STOP\n")
    except Exception:
        pass
    try:
        port.close()
    except Exception:
        pass


def connection_worker(port_name, intent, closing, events, serial_factory=None,
                      clock=time.monotonic):
    """Reconecta por ate 5 s; nunca restaura uma direcao antiga."""
    if serial_factory is None:
        import serial
        serial_factory = serial.Serial
    retry_start = clock()
    try:
        while not closing.is_set():
            port, link = None, None
            try:
                remaining = RECONNECT_WINDOW if retry_start is None else RECONNECT_WINDOW - (clock() - retry_start)
                if remaining <= 0:
                    raise TimeoutError("Prazo de reconexao encerrado")
                port = serial_factory(port_name, 115200, timeout=0.02, write_timeout=0.3,
                                      rtscts=False, dsrdtr=False, xonxoff=False)
                remaining = RECONNECT_WINDOW if retry_start is None else RECONNECT_WINDOW - (clock() - retry_start)
                if remaining <= 0 or closing.is_set():
                    raise TimeoutError("Prazo de reconexao encerrado")
                exchange(port, b"HELLO\n", "POLOLU_CONTROL_V2", timeout=min(1, remaining))
                if closing.is_set():
                    break
                if retry_start is not None and clock() - retry_start >= RECONNECT_WINDOW:
                    raise TimeoutError("Resposta chegou depois do prazo de reconexao")
                events.put(("connected", "Conectado ao receptor · pronto para mover"))
                link = ControlLink(port, clock=clock)
                last_stats = clock()
                while not closing.is_set():
                    request = intent.current()
                    if request is None:
                        left, right = 0, 0
                    else:
                        direction, speed = request
                        factors = DIRECTIONS[direction]
                        left, right = factors[0] * speed, factors[1] * speed
                    link.step(left, right)
                    if link.received:
                        # HELLO sozinho nao basta para reiniciar o prazo de recuperacao.
                        retry_start = None
                    elif retry_start is not None and clock() - retry_start >= RECONNECT_WINDOW:
                        raise TimeoutError("Sem confirmacao de controle no prazo de reconexao")
                    if clock() - last_stats >= 1:
                        stats = link.stats()
                        events.put(("metrics", "Latência p95: %s ms · pendentes: %d · confirmações: %d" %
                                    (stats["p95_ms"], stats["pending"], stats["acknowledged"])))
                        last_stats = clock()
                    closing.wait(0.005)
            except Exception as exc:
                intent.stop()
                if closing.is_set():
                    break
                if retry_start is None:
                    retry_start = link.last_ack if link is not None else clock()
                remaining = RECONNECT_WINDOW - (clock() - retry_start)
                if remaining <= 0:
                    events.put(("error", "Sem comunicação confirmada por 5 s. Reconexão encerrada: %s" % exc))
                    break
                events.put(("reconnecting", "Reconectando em até 1 s · %.1f s restantes · %s" % (remaining, exc)))
                close_port(port)
                port = None
                if closing.wait(min(RETRY_INTERVAL, max(0, RECONNECT_WINDOW - (clock() - retry_start)))):
                    break
            finally:
                close_port(port)
    finally:
        intent.stop()
        events.put(("disconnected", "Desconectado"))


class ControlPanel:
    def __init__(self, root):
        self.root = root
        self.intent = MotionIntent()
        self.events = queue.Queue()
        self.closing = threading.Event()
        self.worker = None
        self.connected = False
        self.exiting = False
        self.held = None
        self.failed = False
        self.port = tk.StringVar(value="/dev/rfcomm0")
        self.speed = tk.IntVar(value=1500)
        self.status = tk.StringVar(value="Desconectado · inicie control_receiver.py no Pololu")
        self.motion = tk.StringVar(value="Parado")
        self.metrics = tk.StringVar(value="Latência: aguardando conexão")
        root.title("POLOLU · Controle Bluetooth")
        root.geometry("660x600")
        root.minsize(620, 580)
        root.configure(bg="#101827")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#101827")
        style.configure("TLabel", background="#101827", foreground="#e6edf7", font=("Sans", 11))
        style.configure("Title.TLabel", font=("Sans", 23, "bold"))
        style.configure("TButton", font=("Sans", 11), padding=10)
        panel = ttk.Frame(root, padding=24)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="POLOLU", style="Title.TLabel").pack(anchor="w")
        ttk.Label(panel, text="Controle do Zumo 2040 por Bluetooth").pack(anchor="w", pady=(3, 18))
        connection = ttk.Frame(panel)
        connection.pack(fill="x")
        ttk.Label(connection, text="Porta").pack(side="left", padx=(0, 8))
        self.entry = ttk.Entry(connection, textvariable=self.port, width=23)
        self.entry.pack(side="left", fill="x", expand=True)
        self.connect_button = ttk.Button(connection, text="Conectar", command=self.connect)
        self.connect_button.pack(side="left", padx=(8, 0))
        self.disconnect_button = ttk.Button(connection, text="Desconectar", command=self.disconnect, state="disabled")
        self.disconnect_button.pack(side="left", padx=(8, 0))
        ttk.Label(panel, textvariable=self.status, wraplength=560).pack(anchor="w", pady=(10, 14))
        speed_row = ttk.Frame(panel)
        speed_row.pack(fill="x")
        ttk.Label(speed_row, text="Velocidade").pack(side="left")
        ttk.Label(speed_row, textvariable=self.speed, width=5).pack(side="right")
        tk.Scale(panel, from_=500, to=3000, resolution=100, orient="horizontal",
                 variable=self.speed, showvalue=False, bg="#101827", fg="#e6edf7",
                 troughcolor="#263449", highlightthickness=0).pack(fill="x")
        pad = ttk.Frame(panel)
        pad.pack(pady=12)
        self.direction_buttons = []
        for text, direction, row, col in (
            ("▲ Frente", "forward", 0, 1), ("◀ Esquerda", "left", 1, 0),
            ("Direita ▶", "right", 1, 2), ("▼ Ré", "backward", 2, 1),
        ):
            button = tk.Button(pad, text=text, width=13, height=2,
                               bg="#253851", fg="white", activebackground="#37567b",
                               activeforeground="white", relief="flat", font=("Sans", 12),
                               state="disabled", takefocus=False)
            button.grid(row=row, column=col, padx=4, pady=4)
            button.bind("<ButtonPress-1>", lambda event, d=direction: self.hold(d))
            button.bind("<Leave>", lambda event: self.stop())
            self.direction_buttons.append(button)
        tk.Button(pad, text="PARAR", width=13, height=2, command=self.stop,
                  bg="#b43443", fg="white", activebackground="#d94355",
                  activeforeground="white", relief="flat", font=("Sans", 12, "bold"),
                  takefocus=False).grid(row=1, column=1, padx=4, pady=4)
        ttk.Label(panel, textvariable=self.motion).pack()
        ttk.Label(panel, textvariable=self.metrics).pack(pady=(6, 0))
        ttk.Label(panel, text="Segure um botão para mover. Solte para parar.\n"
                  "Espaço ou Esc: parar · sair da janela: parar\n"
                  "Movimento contínuo · parada automática se perder comunicação.",
                  justify="center", wraplength=550).pack(pady=(12, 0))
        root.bind_all("<ButtonRelease-1>", lambda event: self.stop(), add="+")
        root.bind("<space>", lambda event: self.stop())
        root.bind("<Escape>", lambda event: self.stop())
        root.bind("<FocusOut>", self.focus_out)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(50, self.tick)

    def hold(self, direction):
        if not self.connected or self.closing.is_set():
            return
        self.held = direction
        self.intent.hold(direction, self.speed.get())
        self.motion.set({"forward": "Frente", "backward": "Ré", "left": "Girando à esquerda",
                         "right": "Girando à direita"}[direction])

    def stop(self):
        self.held = None
        self.intent.stop()
        self.motion.set("Movimento cancelado · enviando parada quando conectado")

    def focus_out(self, event):
        self.root.after_idle(self.check_focus)

    def check_focus(self):
        if self.root.focus_displayof() is None:
            self.stop()

    def connect(self):
        if self.worker is not None and self.worker.is_alive():
            return
        port = self.port.get().strip()
        if not port:
            self.status.set("Informe a porta Bluetooth, por exemplo /dev/rfcomm0")
            return
        self.stop()
        self.failed = False
        self.closing.clear()
        self.connect_button.configure(state="disabled")
        self.entry.configure(state="disabled")
        self.disconnect_button.configure(state="normal")
        self.status.set("Conectando e verificando resposta do receptor…")
        self.worker = threading.Thread(target=connection_worker,
            args=(port, self.intent, self.closing, self.events), daemon=True)
        self.worker.start()

    def disconnect(self):
        self.stop()
        self.closing.set()
        self.connected = False
        self.status.set("Encerrando conexão…")
        for button in self.direction_buttons:
            button.configure(state="disabled")

    def close(self):
        self.exiting = True
        self.disconnect()

    def tick(self):
        while not self.events.empty():
            kind, message = self.events.get_nowait()
            if kind == "connected" and not self.closing.is_set():
                self.connected = True
                self.status.set(message)
                for button in self.direction_buttons:
                    button.configure(state="normal")
            elif kind == "reconnecting":
                self.connected = False
                self.stop()
                self.status.set(message)
                for button in self.direction_buttons:
                    button.configure(state="disabled")
            elif kind == "metrics":
                self.metrics.set(message)
            elif kind == "error":
                self.failed = True
                self.status.set(message)
                self.stop()
            elif kind == "disconnected":
                self.connected = False
                self.stop()
                if not self.failed:
                    self.status.set(message)
                for button in self.direction_buttons:
                    button.configure(state="disabled")
        if self.worker is None or not self.worker.is_alive():
            self.connect_button.configure(state="normal")
            self.entry.configure(state="normal")
            self.disconnect_button.configure(state="disabled")
            if self.exiting:
                self.root.destroy()
                return
        if self.connected and self.held and not self.closing.is_set():
            self.intent.hold(self.held, self.speed.get())
        self.root.after(50, self.tick)


if __name__ == "__main__":
    root = tk.Tk()
    ControlPanel(root)
    root.mainloop()
