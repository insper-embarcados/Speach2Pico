"""Bounded push-to-talk recording; no global keyboard hooks are needed."""

from pathlib import Path
import tempfile
import threading
import wave


class AudioRecorder:
    def __init__(self, device=None, max_seconds=30):
        self.device = device
        self.max_seconds = max_seconds
        self._stream = None
        self._lock = threading.Lock()
        self._chunks = []
        self._frames = 0
        self._error = None
        self._sample_rate = 16000

    def start(self):
        if self._stream is not None:
            raise RuntimeError("Já existe uma gravação em andamento.")
        try:
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise RuntimeError("Instale sounddevice e PortAudio para usar o microfone. Consulte o README.") from exc
        self._chunks = []
        self._frames = 0
        self._error = None
        self._sample_rate = int(sd.query_devices(self.device, "input")["default_samplerate"])
        limit = int(self.max_seconds * self._sample_rate)

        def callback(data, frames, time_info, status):
            with self._lock:
                if status:
                    self._error = str(status)
                take = min(frames, max(0, limit - self._frames))
                if take:
                    self._chunks.append(bytes(data)[:take * 2])
                    self._frames += take

        stream = sd.RawInputStream(
            device=self.device, samplerate=self._sample_rate, channels=1,
            dtype="int16", callback=callback,
        )
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        self._stream = stream

    def _close(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()

    def cancel(self):
        try:
            self._close()
        finally:
            with self._lock:
                self._chunks = []
                self._frames = 0

    def finish(self) -> Path:
        if self._stream is None:
            raise RuntimeError("Não há gravação em andamento.")
        self._close()
        with self._lock:
            chunks, frames, error = self._chunks, self._frames, self._error
            self._chunks = []
            self._frames = 0
        if error:
            raise RuntimeError(f"Falha na captura de áudio: {error}. Tente novamente.")
        if frames < self._sample_rate // 4:
            raise ValueError("Gravação muito curta. Segure espaço por pelo menos 0,25 segundo.")
        with tempfile.NamedTemporaryFile(prefix="speech2pico-", suffix=".wav", delete=False) as file:
            path = Path(file.name)
        try:
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self._sample_rate)
                wav.writeframes(b"".join(chunks))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return path


def list_audio_devices():
    try:
        import sounddevice as sd
        return [(i, d["name"]) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
    except (ImportError, OSError) as exc:
        raise RuntimeError("Captura de áudio indisponível. Instale as dependências do README.") from exc
