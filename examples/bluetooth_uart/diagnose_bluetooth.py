"""Mede o enlace SEM mover motores. Feche a GUI antes de executar."""
import argparse
import json
from pathlib import Path
import time

from control_link import ControlLink
from send_static import expect, write_all


def diagnose(port, duration):
    report = {"mode": "motors_stopped", "duration_requested_s": duration}
    try:
        write_all(port, b"HELLO\n")
        header = bytearray()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not header.endswith(b"\n"):
            header.extend(port.read(1))
        version = bytes(header).strip()
        report["protocol"] = version.decode("ascii", "replace")
        start = time.monotonic()
        if version == b"POLOLU_CONTROL_V2":
            link = ControlLink(port)
            try:
                while time.monotonic() - start < duration:
                    link.step(0, 0)
                    time.sleep(0.005)
            finally:
                report.update(link.stats())
        elif version == b"POLOLU_CONTROL_V1":
            # Baseline do receptor anterior, sem mudar firmware ou mover o robo.
            samples = []
            try:
                while time.monotonic() - start < duration:
                    sent = time.monotonic()
                    write_all(port, b"STOP\n")
                    expect(port, "STOPPED", timeout=2, report=None)
                    samples.append((time.monotonic() - sent) * 1000)
                    time.sleep(0.05)
            finally:
                samples.sort()
                report.update({"acknowledged": len(samples),
                    "median_ms": round(samples[len(samples)//2], 1) if samples else None,
                    "p95_ms": round(samples[min(len(samples)-1, int(len(samples)*0.95))], 1) if samples else None,
                    "max_ms": round(max(samples), 1) if samples else None,
                    "over_500ms": sum(x > 500 for x in samples)})
        else:
            raise RuntimeError("Inicie control_receiver.py no Pololu; resposta: %r" % version)
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        try:
            write_all(port, b"STOP\n")
        except Exception:
            pass
    return report


def main():
    import serial
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/rfcomm0")
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 120:
        parser.error("--seconds deve estar entre 1 e 120")
    try:
        with serial.Serial(args.port, 115200, timeout=0.02, write_timeout=0.3,
                           exclusive=True, rtscts=False, dsrdtr=False, xonxoff=False) as port:
            report = diagnose(port, args.seconds)
    except Exception as exc:
        report = {"mode": "motors_stopped", "error": str(exc)}
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    return 1 if "error" in report else 0


if __name__ == "__main__":
    raise SystemExit(main())
