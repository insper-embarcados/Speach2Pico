"""Renomeia HC-06-20190901 para POLOLU, seguindo a referencia do Insper.

Execute no Zumo 2040 por USB, com o receptor parado e sem conexao Bluetooth
ativa no HC-06. TXD do modulo -> GP29; RXD do modulo -> GP28; GND comum.
Referencia: https://github.com/insper-embarcados/pico-rtos-hc06-rx-tx
Procura a velocidade existente sem alterar baud rate ou PIN. Comandos sem CR/LF.
"""
import time

NAME = "POLOLU"
BAUDRATES = (115200, 9600, 38400, 19200, 57600, 4800, 2400, 1200)
EXPECTED_VERSION = b"HC-06-20190901"
ATTEMPTS = 3
INTERVAL_MS = 5000


def command(uart, text, response_ms=1500):
    # Descarta dados anteriores para nao confundir respostas de comandos.
    uart.read()
    data = text.encode("ascii")
    print("TX:", repr(data))
    if uart.write(data) != len(data):
        raise RuntimeError("Nao foi possivel enviar o comando completo.")
    response = bytearray()
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < response_ms:
        chunk = uart.read(64)
        if chunk:
            response.extend(chunk)
            if len(response) > 256:
                raise RuntimeError("Resposta excessiva; confira modulo e baud rate.")
        time.sleep_ms(10)
    result = bytes(response).strip()
    print("RX:", repr(result) if result else "(sem resposta)")
    return result


def detect_baud(uart, tx, rx):
    for index, baud in enumerate(BAUDRATES):
        if index:
            time.sleep_ms(INTERVAL_MS)
        # O firmware do Zumo exige os pinos novamente em cada UART.init().
        uart.init(baudrate=baud, bits=8, parity=None, stop=1,
                  tx=tx, rx=rx, rxbuf=512, timeout=0, timeout_char=2)
        time.sleep_ms(500)
        for attempt in range(1, ATTEMPTS + 1):
            print("Testando", baud, "baud; tentativa", attempt, "de", ATTEMPTS)
            if command(uart, "AT", response_ms=500) == b"OK":
                print("UART confirmada em", baud, "baud")
                return baud
            if attempt < ATTEMPTS:
                time.sleep_ms(INTERVAL_MS)
    return None


def configure_name(uart, tx, rx):
    print("Aguardando 5 segundos para inicializacao do HC-06...")
    time.sleep_ms(INTERVAL_MS)
    baud = detect_baud(uart, tx, rx)
    if baud is None:
        print("Sem resposta AT nas velocidades", BAUDRATES, ". Nome NAO enviado.")
        print("Confira VCC/GND, TX/RX e ausencia de conexao Bluetooth ativa.")
        print("VSW depende das pilhas e da chave; nao e uma saida regulada de 5 V.")
        return False

    time.sleep_ms(INTERVAL_MS)
    version = command(uart, "AT+VERSION")
    if version != EXPECTED_VERSION:
        print("Firmware diferente da referencia do Insper ou sem resposta.")
        print("Esperado:", EXPECTED_VERSION, "Recebido:", repr(version))
        print("Nome NAO enviado. Guarde esta saida para identificar o firmware.")
        return False

    time.sleep_ms(INTERVAL_MS)
    response = command(uart, "AT+NAME" + NAME)
    if b"OKsetname" not in response:
        print("Comando enviado, mas a alteracao NAO foi confirmada.")
        print("Guarde a resposta RX; nao presuma que o nome mudou.")
        return False

    print("HC-06 confirmou a alteracao do nome para", NAME)
    print("Baud rate do modulo mantido em", baud, "; PIN nao alterado.")
    print("Para enviar codigo, ajuste BAUDRATE =", baud, "em receiver.py.")
    print("Desligue e religue a alimentacao do modulo e faca uma nova busca Bluetooth.")
    return True


def main():
    from machine import Pin, UART
    from zumo_2040_robot import robot

    robot.Motors().off()
    tx, rx = Pin(28), Pin(29)
    uart = UART(0, baudrate=BAUDRATES[0], bits=8, parity=None, stop=1,
                tx=tx, rx=rx, rxbuf=512,
                timeout=0, timeout_char=2)
    try:
        print("HC-06: UART0, TX=GP28, RX=GP29; velocidades:", BAUDRATES)
        print("A busca completa pode levar cerca de 2 a 3 minutos.")
        print("O modulo deve estar alimentado e sem conexao Bluetooth ativa.")
        configure_name(uart, tx, rx)
    finally:
        uart.deinit()


if __name__ == "__main__":
    main()
