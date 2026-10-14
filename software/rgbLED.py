
from machine import Pin
import neopixel
import time

# RGB LED initialize
np = neopixel.NeoPixel(Pin(21), 1)

# define colors as dict
COLORS = {
    "red":     (255, 0, 0),
    "green":   (0, 255, 0),
    "blue":    (0, 0, 255),
    "white":   (255, 255, 255),
    "yellow":  (255, 255, 0),
    "orange":  (255, 80, 0),
    "purple":  (128, 0, 255),
    "pink":    (255, 20, 100),
    "cyan":    (0, 255, 255),
    "turquoise": (0, 255, 150),
    "warmwhite": (255, 180, 90),
    "off":     (0, 0, 0)
}


def set_led(color: str, brightness=100):
    if color not in COLORS:
        print("Unknown color:", color)
        return

    brightness = max(0, min(100, brightness))

    r, g, b = COLORS[color]
    factor = brightness / 100

    np[0] = (
        int(r * factor),
        int(g * factor),
        int(b * factor)
    )
    np.write()


def led_off():
    set_led("off")


def boot_rgb_led():
    # Weiß langsam ausblenden
    for brightness in range(100, -1, -2):
        set_led("white", brightness)
        time.sleep_ms(15)

