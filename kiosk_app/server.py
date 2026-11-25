"""Loopback-only API and prebuilt kiosk assets. No hardware work on HTTP threads."""
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .ai import CloudAI, validate_code
from .audio import AudioRecorder
from .bluetooth import RobotLink
from .wifi import Wifi

ROOT = Path(__file__).resolve().parent.parent
BUSY = {"recording", "transcribing", "generating", "sending", "running"}
DEMO_CODE = '''from zumo_2040_robot import robot
import time

led = robot.YellowLED()
try:
    for _ in range(5):
        led.on()
        time.sleep_ms(250)
        led.off()
        time.sleep_ms(250)
finally:
    led.off()
'''


class Controller:
    def __init__(self, demo=False, link=None, ai=None, wifi=None, recorder=None):
        self.demo = demo
        self.link = link or RobotLink(os.getenv("BLUETOOTH_ADDRESS", "00:23:04:00:33:75"), int(os.getenv("BLUETOOTH_CHANNEL", "1")))
        self.ai = ai or CloudAI()
        self.wifi = wifi or Wifi()
        device = os.getenv("KIOSK_AUDIO_DEVICE")
        self.recorder = recorder or AudioRecorder(device=int(device) if device and device.isdigit() else device)
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.record_timer = None
        self.previous = None
        self.record_modify = False
        self.executions = []
        self.state = dict(phase="idle", text="", code="", mission_id=None, error=None,
                          message="Uma ideia sua. Uma missão do Pololu.", recording_since=None,
                          completed=0, demo=demo)
        self.network = dict(available=False, networks=[], internet="unknown", error=None, busy=False)

    def snapshot(self):
        with self.lock:
            state = dict(self.state)
            state["wifi"] = dict(self.network)
        state["bluetooth"] = (dict(connected=True, phase="connected", name="POLOLU · simulado",
            message="Conexão simulada; nenhum rádio utilizado", attempts=0, uncertain=False,
            latency_ms=None, address="Demonstração", last_seen=None) if self.demo else self.link.snapshot())
        state["providers"] = dict(llm=os.getenv("LLM_PROVIDER", "openai"), stt=os.getenv("STT_PROVIDER", "openai"))
        return state

    def start(self):
        if not self.demo:
            self.link.start()
            threading.Thread(target=self._network_loop, daemon=True).start()
        else:
            self.network.update(available=True, internet="unknown", networks=[
                dict(ssid="Laboratório · exemplo", signal=86, connected=False, security="WPA2"),
                dict(ssid="Oficina · exemplo", signal=62, connected=False, security="WPA2")])

    def close(self):
        self.closed.set()
        if self.record_timer:
            self.record_timer.cancel()
        self.recorder.cancel()
        if not self.demo:
            self.link.close()

    def _network_loop(self):
        while not self.closed.is_set():
            self.refresh_wifi()
            self.closed.wait(10)

    def refresh_wifi(self, rescan=False):
        if self.demo:
            return
        with self.lock:
            if self.network["busy"]:
                return
            self.network["busy"] = True
        try:
            result = self.wifi.snapshot(rescan)
            with self.lock:
                self.network.update(result)
        except Exception as exc:
            with self.lock:
                self.network.update(error=str(exc), available=False, networks=[], internet="unknown")
        finally:
            with self.lock:
                self.network["busy"] = False

    def connect_wifi(self, ssid, password):
        with self.lock:
            if self.network["busy"]:
                raise ValueError("Aguarde a operação de Wi-Fi terminar.")
            if self.demo:
                raise ValueError("O modo demonstração não altera redes Wi-Fi.")
            self.network.update(busy=True, error=None)
        def work():
            try:
                self.wifi.connect(ssid, password)
                result = self.wifi.snapshot()
                with self.lock:
                    self.network.update(result)
            except Exception as exc:
                with self.lock:
                    self.network["error"] = str(exc)
            finally:
                with self.lock:
                    self.network["busy"] = False
        threading.Thread(target=work, daemon=True).start()

    def _ensure_idle(self):
        if self.state["phase"] in BUSY:
            raise ValueError("Já existe uma operação em andamento.")

    def _work(self, fn):
        def wrapped():
            try:
                fn()
            except Exception as exc:
                message = str(exc) if isinstance(exc, (ValueError, RuntimeError, ConnectionError, TimeoutError)) else "O serviço não concluiu o pedido. Confira a configuração, internet e cotas da API."
                with self.lock:
                    self.state.update(phase="error", error=message[:400], message="Vamos tentar de novo?", recording_since=None)
        threading.Thread(target=wrapped, daemon=True).start()

    def generate(self, text, modify=False):
        text = text.strip()
        if not text or len(text) > 2000:
            raise ValueError("Escreva ou dite uma instrução de até 2000 caracteres.")
        with self.lock:
            self._ensure_idle()
            previous = (self.state["code"] or self.previous) if modify else None
            if modify and not previous:
                raise ValueError("Gere uma missão antes de modificá-la.")
            self.previous = previous
            self.state.update(phase="generating", text=text, error=None, code="", mission_id=None,
                              message="Preparando sua missão…")
        def work():
            if self.demo:
                time.sleep(7)
                code = DEMO_CODE
            else:
                code = validate_code(self.ai.generate(text, previous))
            with self.lock:
                self.state.update(phase="ready", code=code, mission_id=uuid.uuid4().hex,
                                  message="Pronto para decolar. Você dá a partida.")
        self._work(work)

    def record_start(self, modify=False):
        with self.lock:
            self._ensure_idle()
            if self.demo:
                raise ValueError("Na demonstração, escreva uma ideia ou escolha um exemplo.")
            if modify and not self.state["code"]:
                raise ValueError("Gere uma missão antes de modificá-la.")
            self.recorder.start()
            self.record_modify = modify
            self.state.update(phase="recording", error=None, recording_since=time.time(), message="Estou ouvindo sua ideia…")
            self.record_timer = threading.Timer(30, self.record_finish)
            self.record_timer.daemon = True
            self.record_timer.start()

    def record_finish(self):
        with self.lock:
            if self.state["phase"] != "recording":
                return
            self.record_timer.cancel()
            self.state.update(phase="transcribing", message="Transformando sua voz em palavras…", recording_since=None)
        def work():
            path = self.recorder.finish()
            try:
                text = self.ai.transcribe(path)
                if not text:
                    raise ValueError("Não consegui reconhecer a fala. Tente novamente.")
                with self.lock:
                    self.state.update(phase="review", text=text[:2000], message="Confira o que você falou e prepare a missão.")
                    self.generate(text[:2000], self.record_modify)
            finally:
                path.unlink(missing_ok=True)
        self._work(work)

    def cancel_recording(self):
        with self.lock:
            if self.state["phase"] != "recording":
                raise ValueError("Não há gravação para cancelar.")
            self.record_timer.cancel()
            self.recorder.cancel()
            self.state.update(phase="idle", recording_since=None, message="Gravação cancelada.")

    def execute(self, mission_id, execution_id=None):
        with self.lock:
            if execution_id and execution_id in self.executions:
                return
            self._ensure_idle()
            if not self.state["code"] or mission_id != self.state["mission_id"]:
                raise ValueError("A missão mudou. Confira o código antes de executar.")
            status = self.snapshot()["bluetooth"]
            if not status["connected"] or status["uncertain"]:
                raise ValueError("Aguarde a conexão e confira se há uma execução incerta.")
            code = self.state["code"]
            if execution_id:
                self.executions = (self.executions + [execution_id])[-100:]
            self.state.update(phase="sending", error=None, message="Enviando a missão ao Pololu…")
        def running():
            with self.lock:
                self.state.update(phase="running", message="Missão em movimento!")
        def work():
            if self.demo:
                running()
                time.sleep(3)
            else:
                self.link.execute(code, running)
            with self.lock:
                self.state.update(phase="done", message="Missão cumprida! Qual é a próxima?", completed=self.state["completed"] + 1)
        self._work(work)

    def reset(self):
        with self.lock:
            self._ensure_idle()
            self.previous = None
            self.state.update(phase="idle", text="", code="", mission_id=None, error=None,
                              message="Uma ideia sua. Uma missão do Pololu.")


class Instruction(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    modify: bool = False


class Mission(BaseModel):
    mission_id: str
    execution_id: str = Field(min_length=8, max_length=64)


class Network(BaseModel):
    ssid: str = Field(min_length=1, max_length=32)
    password: str = Field(default="", max_length=128)


class Recording(BaseModel):
    modify: bool = False


def create_app(controller=None):
    ctl = controller or Controller()

    @asynccontextmanager
    async def lifespan(app):
        ctl.start()
        yield
        ctl.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("origin")
            if request.headers.get("x-kiosk-request") != "1" or (origin and origin != str(request.base_url).rstrip("/")):
                return JSONResponse({"detail": "Pedido não autorizado por esta tela."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(RuntimeError)
    async def unavailable(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.get("/api/status")
    def status():
        return ctl.snapshot()

    @app.post("/api/generate")
    def generate(data: Instruction):
        ctl.generate(data.text, data.modify)
        return ctl.snapshot()

    @app.post("/api/execute")
    def execute(data: Mission):
        ctl.execute(data.mission_id, data.execution_id)
        return ctl.snapshot()

    @app.post("/api/new")
    def reset():
        ctl.reset()
        return ctl.snapshot()

    @app.post("/api/record/start")
    def record(data: Recording):
        ctl.record_start(data.modify)
        return ctl.snapshot()

    @app.post("/api/record/finish")
    def finish():
        ctl.record_finish()
        return ctl.snapshot()

    @app.post("/api/record/cancel")
    def cancel():
        ctl.cancel_recording()
        return ctl.snapshot()

    @app.post("/api/wifi/scan")
    def scan():
        threading.Thread(target=ctl.refresh_wifi, args=(True,), daemon=True).start()
        return {"ok": True}

    @app.post("/api/wifi/connect")
    def connect(data: Network):
        ctl.connect_wifi(data.ssid, data.password)
        return {"ok": True}

    @app.post("/api/bluetooth/acknowledge")
    def acknowledge():
        if ctl.state["phase"] in {"sending", "running"}:
            raise ValueError("Aguarde a execução atual.")
        ctl.link.acknowledge()
        return ctl.snapshot()

    app.mount("/", StaticFiles(directory=Path(__file__).with_name("static"), html=True), name="web")
    return app
