"""demo for one WS2812-compatible RGB LED on GPIO21.

The LED is addressed through its DIN pin (not through ordinary GPIO PWM).
led is set by led[i] = (r, g, b) with i as number of the LED in the row
and r, g, b as intensity of red, green, blue. Followed by
led.write() to set the changes
"""
from machine import Pin
import neopixel
import time

# LED setup
led = neopixel.NeoPixel(Pin(21), 1)

BRIGHTNESS = 0.2

# Rainbow colors
RAINBOW = {
    "red":    (255, 0, 0),
    "orange": (255, 100, 0),
    "yellow": (255, 255, 0),
    "green":  (0, 255, 0),
    "cyan":   (0, 255, 255),
    "blue":   (0, 0, 255),
    "purple": (150, 0, 255)
}

# Main loop
try:
    while True:

        for color, rgb in RAINBOW.items():

            # Set LED color
            led[0] = tuple(
                int(value * BRIGHTNESS) for value in rgb
            )

            led.write()
            time.sleep(1)

finally:
    # Turn LED off when stopped
    led[0] = (0, 0, 0)
    led.write()