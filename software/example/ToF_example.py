"""VL53L0X distance on XIAO ESP32-C3.

Shows distance in millimeters in Thonny every ~100 ms.
Requires vl53l0x_library.py. Is placed next to ToF_example.py
"""

from machine import Pin, I2C
import vl53l0x_library as vl53l0x
import time

# I2C setup
i2c = I2C(0, scl=Pin(7), sda=Pin(6), freq=400000)

try:
    # ToF sensor setup
    sensor = vl53l0x.VL53L0X(i2c)

    sensor.measurement_timing_budget = 33000
    sensor.start_continuous()

    # Main loop
    while True:

        # Read distance in millimeters
        distance = sensor.range

        print("Distance:", distance, "mm")

        time.sleep(0.2)

except OSError:
    print("Failed initialization; unable to build I2C connection; sensor unpluged ?")

except RuntimeError:
    print("maybe cut power, wait a few seconds and try again")
