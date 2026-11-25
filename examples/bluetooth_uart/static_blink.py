"""Codigo fixo enviado pelo Bluetooth: cinco piscadas, sem movimento."""
from zumo_2040_robot import robot
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
