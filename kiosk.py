#!/usr/bin/env python3
"""Run the Raspberry Pi kiosk: python kiosk.py [--demo] [--no-browser]."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Interface simulada; não usa APIs, rádio, microfone ou Wi-Fi")
    parser.add_argument("--no-browser", action="store_true", help="Inicia apenas o servidor local")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--install-autostart", action="store_true", help="Inicia o quiosque ao entrar na sessão gráfica")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if args.install_autostart:
        target = Path.home() / ".config/autostart/speech2pico.desktop"
        target.parent.mkdir(parents=True, exist_ok=True)
        def quote(value):
            return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
        target.write_text("[Desktop Entry]\nType=Application\nName=Speech2Pico\nExec=" + quote(sys.executable) + " " + quote(root / "kiosk.py") + "\nTerminal=false\nX-GNOME-Autostart-enabled=true\n", encoding="utf-8")
        print(f"Inicialização automática instalada: {target}. Ative o login automático na sessão gráfica da Raspi.")
        return 0
    try:
        from dotenv import load_dotenv
        load_dotenv(root / ".env")
        import uvicorn
        from kiosk_app.server import Controller, create_app
    except ImportError as exc:
        print(f"Dependência ausente: {exc}. Execute python -m pip install -r requirements.txt", file=sys.stderr)
        return 1
    if not (root / "kiosk_app/static/index.html").exists():
        print("Interface compilada não encontrada em kiosk_app/static.", file=sys.stderr)
        return 1
    if not 1024 <= args.port <= 65535:
        parser.error("A porta deve estar entre 1024 e 65535.")
    # Fail before starting radio threads or launching a browser if the port is used.
    probe = socket.socket()
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("127.0.0.1", args.port))
    except OSError:
        print(f"Porta {args.port} ocupada. Encerre a outra instância do quiosque.", file=sys.stderr)
        return 1
    finally:
        probe.close()
    url = f"http://127.0.0.1:{args.port}"
    browser_process = []
    stopping = threading.Event()
    def browser():
        executable = next((shutil.which(name) for name in ("chromium", "chromium-browser", "google-chrome") if shutil.which(name)), None)
        if not executable:
            print(f"Chromium não encontrado. Abra {url} ou instale chromium.")
            return
        for _ in range(60):
            if stopping.wait(0.5):
                return
            try:
                with urllib.request.urlopen(url + "/api/status", timeout=1) as response:
                    if response.status == 200:
                        profile = Path.home() / ".local/share/speech2pico/chromium"
                        browser_process.append(subprocess.Popen([executable, "--kiosk", "--no-first-run",
                            "--noerrdialogs", "--disable-session-crashed-bubble", "--password-store=basic",
                            f"--user-data-dir={profile}", url]))
                        return
            except OSError:
                continue
    if not args.no_browser:
        threading.Thread(target=browser, daemon=True).start()
    print(f"Base de lançamento: {url}" + (" · DEMONSTRAÇÃO" if args.demo else ""))
    try:
        uvicorn.run(create_app(Controller(demo=args.demo)), host="127.0.0.1", port=args.port, access_log=False)
    finally:
        stopping.set()
        for process in browser_process:
            process.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
