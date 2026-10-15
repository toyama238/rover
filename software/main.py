from machine import Pin, PWM, ADC, I2C
import random
import time
import webserver
import vl53l0x
import rgbLED

# ===========================================================
# 1. CONFIGURATION
# ===========================================================

# Generall
state = 0  # 0 = smartphone controll, 1 = obstacle avoidance, 2 = following line
MANUAL_SPEED = 70  # general speed
LOOP_PAUSE_MS = 5
DEBUG_INTERVAL_MS = 1000

# following line
LINE_SPEED = 60  # speed for following the
KP = 70
SEARCH_SPEED = 35
MAX_CORRECTION = 75
MAX_SEARCH_TIME = 2000
LINE_THRESHOLD = 30000
DARK_IS_LOW = True

# obstacle avoidance
OBSTACLE_DISTANCE = 350
AUTO_SPEED = 70
EXTRA_TURN_TIME = 50
MAX_TURN_TIME = 5000  # time until path finding failure
TOF_INTERVAL_MS = 50
TOF_TIMEOUT_MS = 500

# Button
DEBOUNCE_MS = 50


# ===========================================================
# 2. initialize hardware
# ===========================================================

# ToF (VL53L0X) via I2C
# GPIO6 = SDA, GPIO7 = SCL

i2c = I2C(0, scl=Pin(7), sda=Pin(6), freq=400000)

vl53 = vl53l0x.VL53L0X(i2c)
vl53.measurement_timing_budget = 33000
vl53.start_continuous()

# motor
left_motor_1 = PWM(Pin(10), freq=200, duty=0)
left_motor_2 = PWM(Pin(8), freq=200, duty=0)
right_motor_1 = PWM(Pin(9), freq=200, duty=0)
right_motor_2 = PWM(Pin(20), freq=200, duty=0)

# button at GPIO4, with pull-up
button = Pin(4, Pin.IN, Pin.PULL_UP)

# analog brightness sensors
line_left = ADC(Pin(2))
line_right = ADC(Pin(3))


# ===========================================================
# 3. runtime variables and timers
# ===========================================================

start_time = time.ticks_ms()

ToF_timer = start_time
debug_timer = start_time

# ToF distance in millimeters
distance = 0
last_valid_tof = None

# obstacle avoidance
changing_direction = False
clear_distance_timer = None
turn_start_timer = None
turn_direction = 0
turn_failed = False

# line following
last_line_direction = 0  # -1 = left, +1 = right
line_lost_timer = None

# button debounce
last_button_state = button.value()
stable_button_state = last_button_state
last_button_time = start_time


# ===========================================================
# 4. motor functions
# ===========================================================


def procent_in_PWM(procent):
    """converts 0–100 % to a 10-bit PWM value."""
    procent = max(0, min(100, procent))
    return int(procent * 1023 / 100)


def set_left_motor(procent):
    """positive = forward, negative = backward."""
    if procent >= 0:
        left_motor_2.duty(0)
        left_motor_1.duty(procent_in_PWM(procent))
    else:
        left_motor_1.duty(0)
        left_motor_2.duty(procent_in_PWM(-procent))


def set_right_motor(procent):
    """positive = forward, negative = backward."""
    if procent >= 0:
        right_motor_2.duty(0)
        right_motor_1.duty(procent_in_PWM(procent))
    else:
        right_motor_1.duty(0)
        right_motor_2.duty(procent_in_PWM(-procent))


def drive(left_speed, right_speed):
    """controls both motors separately in percent (-100 to +100)."""
    set_left_motor(left_speed)
    set_right_motor(right_speed)


def stop_motors():
    """stops both motors."""
    drive(0, 0)


def drive_straight(speed):
    """Drive straight with persistent left/right trim from the webserver.

    Positive calibration strengthens the left motor and weakens the right.
    The same trim applies in reverse with the speed sign preserved.
    Turning in place and the line-following P-controller are unaffected.
    """
    if speed == 0:
        stop_motors()
        return

    trim = webserver.get_calibration()
    direction = 1 if speed > 0 else -1
    magnitude = abs(speed)

    left_magnitude = max(0, min(100, magnitude + trim))
    right_magnitude = max(0, min(100, magnitude - trim))

    drive(direction * left_magnitude, direction * right_magnitude)


# ===========================================================
# 5. line sensors
# ===========================================================


def isDark(value):
    """detects black using the calibrated ADC threshold."""
    if DARK_IS_LOW:
        return value < LINE_THRESHOLD
    else:
        return value > LINE_THRESHOLD


def isLight(value):
    return not isDark(value)


# ===========================================================
# 6. change mode
# ===========================================================


def set_mode(new_state):
    global state
    global changing_direction, clear_distance_timer
    global turn_start_timer, turn_direction, turn_failed
    global last_line_direction, line_lost_timer

    new_state = new_state % 3

    if new_state == state:
        return

    # stop motors before changing mode
    stop_motors()

    # reset active control states
    changing_direction = False
    clear_distance_timer = None
    turn_start_timer = None
    turn_direction = 0
    turn_failed = False

    last_line_direction = 0
    line_lost_timer = None

    state = new_state
    webserver.set_state(state)

    # show current mode with RGB LED
    if state == 0:
        rgbLED.set_led("red", 30)
    elif state == 1:
        rgbLED.set_led("blue", 30)
    elif state == 2:
        rgbLED.set_led("yellow", 30)


# ===========================================================
# 7. start
# ===========================================================

stop_motors()

webserver.start_webserver()
webserver.set_state(state)
webserver.set_distance(0)

rgbLED.boot_rgb_led()
rgbLED.set_led("red", 30)

print("Rover gestartet")


# ===========================================================
# 8. main loop
# ===========================================================

try:
    while True:
        # measure loop execution time without sleep()
        loop_start = time.ticks_us()
        now = time.ticks_ms()

        # ---------------------------------------------------
        # 8.1 handle webserver requests
        # ---------------------------------------------------
        webserver.update_webserver()
        command = webserver.get_command()

        # ---------------------------------------------------
        # 8.2 change mode via web interface
        # ---------------------------------------------------
        if command == "mode_next":
            set_mode(state + 1)
        elif command == "mode_prev":
            set_mode(state - 1)
        elif command == "state":
            # compatibility with older webserver versions
            set_mode(state + 1)

        # ---------------------------------------------------
        # 8.3 debounce physical button
        # ---------------------------------------------------
        button_state = button.value()

        if button_state != last_button_state:
            last_button_time = now

        # accept button changes only after 50 ms of stable input
        if time.ticks_diff(now, last_button_time) >= DEBOUNCE_MS:
            if button_state != stable_button_state:
                stable_button_state = button_state

                # pull-up: 0 means pressed
                if stable_button_state == 0:
                    set_mode(state + 1)

        last_button_state = button_state

        # ---------------------------------------------------
        # 8.4 update distance sensor
        # ---------------------------------------------------
        if time.ticks_diff(now, ToF_timer) >= TOF_INTERVAL_MS:
            ToF_timer = now

            try:
                reading = vl53.range

                # validate reading; adjust limits for the sensor driver if needed
                if 0 < reading < 8190:
                    distance = reading
                    last_valid_tof = now
                    webserver.set_distance(distance)
            except Exception as error:
                print("ToF error:", error)

        # do not drive with outdated distance readings
        tof_ok = False
        if last_valid_tof is not None:
            if time.ticks_diff(now, last_valid_tof) < TOF_TIMEOUT_MS:
                tof_ok = True

        # ---------------------------------------------------
        # 8.5 read line sensors
        # ---------------------------------------------------
        sensLinks = line_left.read_u16()
        sensRechts = line_right.read_u16()

        # ---------------------------------------------------
        # 8.6 STATE 0: manual control
        # ---------------------------------------------------
        if state == 0:
            if command == "forward":
                drive_straight(MANUAL_SPEED)
            elif command == "backward":
                drive_straight(-MANUAL_SPEED)
            elif command == "left":
                drive(-MANUAL_SPEED, MANUAL_SPEED)
            elif command == "right":
                drive(MANUAL_SPEED, -MANUAL_SPEED)
            elif command == "stop":
                stop_motors()

            # no WLAN watchdog yet: if the connection is lost,
            # the last driving command may remain active.

        # ---------------------------------------------------
        # 8.7 STATE 1: obstacle avoidance
        # ---------------------------------------------------
        elif state == 1:
            if turn_failed:
                # turn timeout: stop until the next mode change
                stop_motors()
                rgbLED.set_led("orange", 100)

            else:
                if not changing_direction:
                    if distance <= OBSTACLE_DISTANCE:
                        # obstacle found -> changing direction
                        changing_direction = True
                        clear_distance_timer = None
                        turn_start_timer = now

                        if random.randint(0, 1) == 0:
                            turn_direction = -1
                        else:
                            turn_direction = 1
                    else:
                        drive_straight(AUTO_SPEED)

                if changing_direction:
                    if time.ticks_diff(now, turn_start_timer) >= MAX_TURN_TIME:
                        stop_motors()
                        changing_direction = False
                        clear_distance_timer = None
                        turn_failed = True
                    else:
                        if turn_direction == -1:
                            drive(-AUTO_SPEED, AUTO_SPEED)
                        else:
                            drive(AUTO_SPEED, -AUTO_SPEED)

                        if distance > OBSTACLE_DISTANCE:
                            if clear_distance_timer is None:
                                clear_distance_timer = now
                            elif (
                                time.ticks_diff(now, clear_distance_timer)
                                >= EXTRA_TURN_TIME
                            ):
                                changing_direction = False
                                clear_distance_timer = None
                                drive_straight(AUTO_SPEED)
                        else:
                            clear_distance_timer = None

        # ---------------------------------------------------
        # 8.8 STATE 2: P-controller with line search
        # ---------------------------------------------------
        elif state == 2:
            left_dark = isDark(sensLinks)
            right_dark = isDark(sensRechts)

            if not left_dark and not right_dark:
                # both sensors detect white -> line may be lost
                # works only if at least one sensor normally
                # detects black while following the line.
                if line_lost_timer is None:
                    line_lost_timer = now

                search_time = time.ticks_diff(now, line_lost_timer)

                if search_time >= MAX_SEARCH_TIME:
                    stop_motors()
                elif last_line_direction == -1:
                    drive(-SEARCH_SPEED, SEARCH_SPEED)
                elif last_line_direction == 1:
                    drive(SEARCH_SPEED, -SEARCH_SPEED)
                else:
                    stop_motors()

            else:
                # line detected: proportional control
                line_lost_timer = None

                error = (sensLinks - sensRechts) / 65535
                correction = KP * error
                correction = max(-MAX_CORRECTION, min(MAX_CORRECTION, correction))

                if left_dark and not right_dark:
                    last_line_direction = -1
                elif right_dark and not left_dark:
                    last_line_direction = 1

                left_speed = LINE_SPEED + correction
                right_speed = LINE_SPEED - correction

                left_speed = max(-100, min(100, left_speed))
                right_speed = max(-100, min(100, right_speed))

                drive(int(left_speed), int(right_speed))

        # ---------------------------------------------------
        # 8.9 send performance data to webserver
        # ---------------------------------------------------
        loop_duration_us = time.ticks_diff(time.ticks_us(), loop_start)
        webserver.set_loop_time(loop_duration_us)

        # ---------------------------------------------------
        # 8.10 console debug (once per second)
        # ---------------------------------------------------
        if time.ticks_diff(now, debug_timer) >= DEBUG_INTERVAL_MS:
            debug_timer = now

        time.sleep_ms(LOOP_PAUSE_MS)

except KeyboardInterrupt:
    print("Programm gestoppt")
finally:
    stop_motors()
