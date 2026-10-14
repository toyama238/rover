"""Motor example for Seeed XIAO ESP32-C3 rover.

Sequence: forward -> rotate left -> rotate right -> backward -> stop.
Place the rover on a stand with its wheels off the ground first.
"""
from machine import Pin, PWM
import time

# Four motor-driver inputs used by the rover project.
left_forward = PWM(Pin(10), freq=200, duty=0)
left_backward = PWM(Pin(8), freq=200, duty=0)
right_forward = PWM(Pin(9), freq=200, duty=0)
right_backward = PWM(Pin(20), freq=200, duty=0)

TEST_SPEED = 60  # percent; start cautiously


def pwm_percent(percent):
    """Convert 0..100 percent into 10-bit PWM duty (0..1023)."""
    percent = max(0, min(100, abs(percent)))
    return int(percent * 1023 / 100)


def set_motor(forward_pwm, backward_pwm, speed):
    """Positive speed = forward; negative speed = backward."""
    # First switch both directions off to avoid driving both inputs at once.
    forward_pwm.duty(0)
    backward_pwm.duty(0)
    if speed > 0:
        forward_pwm.duty(pwm_percent(speed))
    elif speed < 0:
        backward_pwm.duty(pwm_percent(speed))


def drive(left_speed, right_speed):
    """Drive the left and right motors independently."""
    set_motor(left_forward, left_backward, left_speed)
    set_motor(right_forward, right_backward, right_speed)


def stop():
    drive(0, 0)


def step(label, left, right, duration_ms):
    print(label, '| left:', left, '| right:', right)
    drive(left, right)
    time.sleep_ms(duration_ms)
    stop()
    time.sleep_ms(400)


try:
    stop()
    print('Motor test starts in 5 seconds. Lift the wheels first!')
    for i in range(5):
        print(5 - i)
        time.sleep_ms(1000)

    step('Forward', TEST_SPEED, TEST_SPEED, 1200)
    step('Rotate left', -TEST_SPEED, TEST_SPEED, 800)
    step('Rotate right', TEST_SPEED, -TEST_SPEED, 800)
    step('Backward', -TEST_SPEED, -TEST_SPEED, 1200)
    print('Motor test finished.')
finally:
    # Stop on normal exit and also on Ctrl+C or an exception.
    stop()
    left_forward.deinit()
    left_backward.deinit()
    right_forward.deinit()
    right_backward.deinit()
