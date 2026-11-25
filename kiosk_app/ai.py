"""Cloud providers used by Speach2Pico; no local model on the Pi 3B."""
import ast
import os
import re
from pathlib import Path


def validate_code(code):
    if not isinstance(code, str) or not 0 < len(code.encode("utf-8")) <= 4096:
        raise ValueError("A IA deve retornar um programa de até 4096 bytes.")
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            if any(n not in {"time", "math", "zumo_2040_robot"} for n in names):
                raise ValueError("O programa usa módulos fora do escopo do robô.")
        if isinstance(node, ast.Name) and (node.id.startswith("__") or node.id in {"eval", "exec", "open", "compile", "globals", "locals", "getattr", "setattr", "delattr", "breakpoint"}):
            raise ValueError("O programa contém uma operação não permitida.")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError("O programa contém acesso a atributos internos.")
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value:
            raise ValueError("Peça uma missão com duração finita, sem laço infinito.")
    return code


class CloudAI:
    def generate(self, instruction, previous=None):
        provider = os.getenv("LLM_PROVIDER", "openai")
        model = os.getenv("LLM_MODEL", "gpt-4.1-mini" if provider == "openai" else "")
        if not model:
            raise ValueError("Configure LLM_MODEL no arquivo .env.")
        prompt = Path(__file__).with_name("prompts").joinpath("zumo.md").read_text()
        prompt += """\n\nRegras específicas do quiosque, substituem as regras 3 e 5 acima:
A missão será revisada e iniciada por um clique explícito em DECOLAR na Raspberry Pi.
Não espere botão A: esse clique é a autorização de início.
Gere apenas missões FINITAS, de no máximo 60 segundos, no máximo 4096 bytes UTF-8.
Nunca gere laços infinitos ou espere indefinidamente um sensor/botão. Use prazo finito.
Sempre desligue motores em finally; limite velocidades absolutas a 1500.
Se não for possível cumprir o pedido dentro dessas regras, responda com texto de recusa, não código.
Não altere UART, Bluetooth, arquivos, rede ou o receptor.
"""
        user = instruction
        if previous:
            user = "Modifique este programa conforme o pedido.\nPrograma anterior:\n" + previous + "\nPedido:\n" + instruction
        if provider == "anthropic":
            from anthropic import Anthropic
            response = Anthropic(timeout=90, max_retries=0).messages.create(
                model=model, max_tokens=2200, system=prompt, messages=[{"role": "user", "content": user}])
            raw = "\n".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        elif provider in ("openai", "nvidia"):
            from openai import OpenAI
            key = os.getenv("NVIDIA_API_KEY" if provider == "nvidia" else "OPENAI_API_KEY")
            if not key:
                raise ValueError(f"Configure a chave de API do provedor {provider} no .env.")
            client = OpenAI(api_key=key, timeout=90, max_retries=0,
                            **({"base_url": os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")} if provider == "nvidia" else {}))
            response = client.chat.completions.create(model=model, max_tokens=8192,
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user}])
            raw = response.choices[0].message.content or ""
        else:
            raise ValueError("LLM_PROVIDER deve ser openai, anthropic ou nvidia.")
        match = re.search(r"```(?:python|micropython)?\s*\n(.*?)```", raw, re.S)
        return validate_code((match.group(1) if match else raw).strip())

    def transcribe(self, path):
        provider = os.getenv("STT_PROVIDER", "openai")
        if provider == "nvidia":
            try:
                import riva.client
            except ImportError:
                raise RuntimeError("Para STT NVIDIA, instale requirements-nvidia.txt.") from None
            auth = riva.client.Auth(uri=os.getenv("NVIDIA_RIVA_SERVER", "grpc.nvcf.nvidia.com:443"), use_ssl=True,
                metadata_args=[["function-id", os.getenv("STT_FUNCTION_ID", "b702f636-f60c-4a3d-a6f4-f3568c13bd7d")],
                               ["authorization", "Bearer " + os.environ["NVIDIA_API_KEY"]]])
            config = riva.client.RecognitionConfig(language_code=os.getenv("STT_LANGUAGE", "pt"),
                max_alternatives=1, enable_automatic_punctuation=True)
            riva.client.add_audio_file_specs_to_config(config, path)
            # Explicit gRPC deadline, unlike the legacy helper's unlimited call.
            import riva.client.proto.riva_asr_pb2 as rasr
            request = rasr.RecognizeRequest(config=config, audio=path.read_bytes())
            response = riva.client.ASRService(auth).stub.Recognize(request, metadata=auth.get_auth_metadata(), timeout=90)
            return " ".join(r.alternatives[0].transcript for r in response.results if r.alternatives).strip()
        if provider == "google":
            from google.cloud import speech
            response = speech.SpeechClient().recognize(
                config=speech.RecognitionConfig(language_code="pt-BR", enable_automatic_punctuation=True),
                audio=speech.RecognitionAudio(content=path.read_bytes()), timeout=90)
            return " ".join(r.alternatives[0].transcript for r in response.results if r.alternatives).strip()
        if provider != "openai":
            raise ValueError("STT_PROVIDER deve ser openai, nvidia ou google.")
        from openai import OpenAI
        with path.open("rb") as audio:
            return OpenAI(timeout=90, max_retries=0).audio.transcriptions.create(
                model=os.getenv("STT_MODEL", "whisper-1"), file=audio, language="pt").text.strip()
