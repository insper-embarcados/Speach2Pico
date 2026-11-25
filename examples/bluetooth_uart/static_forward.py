"""Anda para frente por 5 segundos imediatamente, sem esperar botao."""
from zumo_2040_robot import robot
import time

motors = robot.Motors()
try:
    motors.set_speeds(1500, 1500)
    time.sleep_ms(5000)
finally:
    motors.off()
