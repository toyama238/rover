"""Two analog reflectance / brightness sensors

GPIO2 = left sensor, GPIO3 = right sensor. These sensors measure light
intensity (reflection), NOT a color such as red or green.
"""
from machine import Pin, ADC, PWM
import time

left_sensor = ADC(Pin(2))
right_sensor = ADC(Pin(3))



THRESHOLD = 30000      # calibrate from measured dark/light values
DARK_IS_LOW = True     # set False if black produces higher ADC values
TEST_DURATION_MS = 60000


def is_dark(value):
    """Classify the reflection using the chosen threshold."""
    if DARK_IS_LOW:
        return value < THRESHOLD
    return value > THRESHOLD

start = time.ticks_ms()
print('Brightness test: hold GPIO4 button to enable motors.')
print('Put white/black paper underneath each sensor to test.')

while time.ticks_diff(time.ticks_ms(), start) < TEST_DURATION_MS:
    left_value = left_sensor.read_u16()
    right_value = right_sensor.read_u16()
    left_dark = is_dark(left_value)
    right_dark = is_dark(right_value)

    print('Left:', left_value, 'Right:', right_value,
          '| dark:', left_dark, right_dark)
    time.sleep_ms(150)
print('Test duration reached.')

