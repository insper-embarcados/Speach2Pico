"""NetworkManager integration; passwords go to stdin, never the command line."""
import os
import subprocess
import threading


def split_fields(line):
    fields, current, escaped = [], "", False
    for char in line:
        if escaped:
            current += char
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append(current)
            current = ""
        else:
            current += char
    fields.append(current)
    return fields


class Wifi:
    def __init__(self, runner=subprocess.run):
        self.runner = runner
        self.lock = threading.Lock()

    def command(self, args, password=None, timeout=15):
        try:
            result = self.runner(["nmcli", *args], input=password, text=True,
                                 capture_output=True, timeout=timeout,
                                 env={**os.environ, "LC_ALL": "C"})
        except FileNotFoundError:
            raise RuntimeError("NetworkManager não encontrado. Instale network-manager na Raspberry Pi.") from None
        except subprocess.TimeoutExpired:
            raise RuntimeError("O Wi-Fi demorou para responder. Confira a rede e tente novamente.") from None
        if result.returncode:
            # nmcli can echo prompts/secrets: never return raw stdout/stderr here.
            raise RuntimeError("Não foi possível alterar o Wi-Fi. Confira a senha, o sinal e as permissões do NetworkManager.")
        return result.stdout

    def snapshot(self, rescan=False):
        with self.lock:
            output = self.command(["-t", "--escape", "yes", "-f", "IN-USE,SSID,SIGNAL,SECURITY",
                                   "device", "wifi", "list", "--rescan", "yes" if rescan else "no"])
            networks = {}
            for line in output.splitlines():
                fields = split_fields(line)
                if len(fields) != 4 or not fields[1]:
                    continue
                active, ssid, strength, security = fields
                item = dict(ssid=ssid, signal=int(strength) if strength.isdigit() else 0,
                            security=security, connected=active == "*")
                previous = networks.get(ssid)
                if previous is None or item["connected"] or (not previous["connected"] and item["signal"] > previous["signal"]):
                    networks[ssid] = item
            connectivity = self.command(["-t", "-f", "CONNECTIVITY", "general"]).strip()
            return dict(networks=sorted(networks.values(), key=lambda n: (not n["connected"], -n["signal"])),
                        internet=connectivity, available=True, error=None)

    def connect(self, ssid, password):
        if not ssid or len(ssid.encode()) > 32 or any(c in ssid + password for c in "\n\r\x00"):
            raise ValueError("Nome de rede ou senha inválidos.")
        with self.lock:
            self.command(["--wait", "30", "--ask", "device", "wifi", "connect", ssid],
                         password=password + "\n", timeout=40)
