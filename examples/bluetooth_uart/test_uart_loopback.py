"""Teste fisico da UART0 do Zumo 2040, SEM HC-06 conectado aos sinais.

Com tudo desligado, retire TXD/RXD do HC-06 dos pinos do Zumo e coloque
um jumper entre GP28 e GP29. Religue o Zumo pela USB e execute este script.
Nao ligue nenhum desses pinos a VCC. Remova o jumper antes de reconectar o HC-06.
"""
import time


def main():
    from machine import Pin, UART
    from zumo_2040_robot import robot

    robot.Motors().off()
    print("Teste UART0: requer jumper GP28 <-> GP29 e HC-06 fora dessas linhas.")
    all_ok = True
    for baud in (9600, 115200):
        uart = UART(0, baudrate=baud, bits=8, parity=None, stop=1,
                    tx=Pin(28), rx=Pin(29), rxbuf=512,
                    timeout=0, timeout_char=2)
        try:
            time.sleep_ms(100)
            uart.read()
            message = ("POLOLU-UART0-%d\n" % baud).encode()
            sent = uart.write(message)
            received = bytearray()
            start = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), start) < 1000:
                chunk = uart.read(64)
                if chunk:
                    received.extend(chunk)
                    if len(received) >= len(message):
                        break
                time.sleep_ms(5)
            print("Baud:", baud, "TX:", repr(message), "RX:", repr(bytes(received)))
            ok = sent == len(message) and bytes(received) == message
            print("PASSOU" if ok else "FALHOU: confira jumper e identificacao GP28/GP29.")
            all_ok = all_ok and ok
        finally:
            uart.deinit()
    if all_ok:
        print("UART0 confirmada por loopback nas duas velocidades.")
        print("Isso nao testa alimentacao, firmware ou funcionamento do HC-06.")
    print("Desligue o Zumo e remova o jumper antes de reconectar o modulo.")


if __name__ == "__main__":
    main()
