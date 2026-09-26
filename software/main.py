from machine import Pin, PWM, ADC
import machine
import time
import webserver
import vl53l0x

# ToF -------------------------------------------------------
i2c = machine.I2C(
    0,
    scl=machine.Pin(7),
    sda=machine.Pin(6),
    freq=400000
)

vl53 = vl53l0x.VL53L0X(i2c)
vl53.measurement_timing_budget = 33000
vl53.start_continuous()

ToF_timer = time.ticks_ms()


# Motors ----------------------------------------------------
left_motor_1 = PWM(Pin(10), freq=200, duty=0)
left_motor_2 = PWM(Pin(8),  freq=200, duty=0)
right_motor_1 = PWM(Pin(9), freq=200, duty=0)
right_motor_2 = PWM(Pin(20), freq=200, duty=0)


# LED -------------------------------------------------------
led = Pin(21, Pin.OUT)
led_timer = time.ticks_ms()


# Variables -------------------------------------------------
state = 0
speed = 75

left_target = 0
right_target = 0

left_current = 0
right_current = 0

motor_ramp_timer = time.ticks_ms()

MIN_SPEED = 60
RAMP_STEP = 1
RAMP_INTERVAL = 66


# Line sensors ----------------------------------------------

line_left  = ADC( Pin( 2 ) )
line_right = ADC( Pin( 3 ) )


# PID -------------------------------------------------------

KP = 0.04
KI = 0.0
KD = 0.02

pid_integral = 0
pid_last_error = 0

pid_timer = time.ticks_ms()

PID_INTERVAL = 20       # alle 20 ms
LINE_SPEED = 65


def procent_in_PWM(procent: int):
    if procent < 0:
        procent = 0
    elif procent > 100:
        procent = 100

    return int(procent * 1023 / 100)


def set_left_motor(procent: int):
    if procent >= 0:
        left_motor_1.duty(procent_in_PWM(procent))
        left_motor_2.duty(0)
    else:
        left_motor_1.duty(0)
        left_motor_2.duty(procent_in_PWM(-procent))


def set_right_motor(procent: int):
    if procent >= 0:
        right_motor_1.duty(procent_in_PWM(procent))
        right_motor_2.duty(0)
    else:
        right_motor_1.duty(0)
        right_motor_2.duty(procent_in_PWM(-procent))


def set_motor_target(left, right):
    global left_target, right_target

    left_target = left
    right_target = right


def stop_motors():
    set_motor_target(0, 0)


def move_towards(current, target, step):

    # Motor soll stehen
    if target == 0:
        return 0

    # Motor startet aus Stillstand
    if current == 0:
        if target > 0:
            return MIN_SPEED
        else:
            return -MIN_SPEED

    # Richtung wechseln:
    # erst Richtung 0 fahren
    if current > 0 and target < 0:
        current -= step

        if current < 0:
            current = 0

        return current

    if current < 0 and target > 0:
        current += step

        if current > 0:
            current = 0

        return current

    # normale Rampe
    if current < target:
        current += step

        if current > target:
            current = target

    elif current > target:
        current -= step

        if current < target:
            current = target

    return current


def update_motors(now):
    global left_current
    global right_current
    global motor_ramp_timer

    if time.ticks_diff(now, motor_ramp_timer) < RAMP_INTERVAL:
        return

    motor_ramp_timer = now

    left_current = move_towards(
        left_current,
        left_target,
        RAMP_STEP
    )

    right_current = move_towards(
        right_current,
        right_target,
        RAMP_STEP
    )

    set_left_motor(left_current)
    set_right_motor(right_current)
    

def update_line_follower(now):
    global pid_integral
    global pid_last_error
    global pid_timer

    if time.ticks_diff(now, pid_timer) < PID_INTERVAL:
        return

    pid_timer = now

    # Sensoren auslesen
    left_value = line_left.read_u16()
    right_value = line_right.read_u16()

    # Fehler:
    # 0 = Linie mittig
    # positiv = Abweichung in eine Richtung
    # negativ = andere Richtung
    error = left_value - right_value

    # Integral
    pid_integral += error

    # Integral begrenzen
    pid_integral = max(
        -100000,
        min(100000, pid_integral)
    )

    # Differential
    derivative = error - pid_last_error

    pid_last_error = error

    # PID-Ausgang
    correction = (
        KP * error
        + KI * pid_integral
        + KD * derivative
    )

    # Korrektur begrenzen
    correction = max(
        -LINE_SPEED,
        min(LINE_SPEED, correction)
    )

    left_speed = LINE_SPEED - correction
    right_speed = LINE_SPEED + correction

    # auf -100 ... 100 begrenzen
    left_speed = max(-100, min(100, left_speed))
    right_speed = max(-100, min(100, right_speed))

    set_motor_target(
        int(left_speed),
        int(right_speed)
    )


webserver.start_webserver()


while True:

    now = time.ticks_ms()


    # -------------------------------------------------------
    # Webserver
    # -------------------------------------------------------

    webserver.update_webserver()

    command = webserver.get_command()


    if command == "state":
        state = (state + 1) % 3

        stop_motors()

        webserver.set_state(state)

        print("State:", state)


    # -------------------------------------------------------
    # STATE 0: Remote Control
    # -------------------------------------------------------

    if state == 0:

        led.value(True)

        if command == "forward":
            set_motor_target(speed, speed)

        elif command == "backward":
            set_motor_target(-speed, -speed)

        elif command == "left":
            set_motor_target(-speed, speed)

        elif command == "right":
            set_motor_target(speed, -speed)

        elif command == "stop":
            stop_motors()


    # -------------------------------------------------------
    # STATE 1: Autonomous
    # -------------------------------------------------------

    elif state == 1:

        if time.ticks_diff(now, led_timer) >= 500:
            led_timer = now
            led.value(not led.value())


        if time.ticks_diff(now, ToF_timer) >= 1000:
            ToF_timer = now

            distance = vl53.range

            webserver.set_distance(distance)
            
    # -------------------------------------------------------
    # STATE 2: Following line
    # -------------------------------------------------------
    
    elif state == 2:
    
        update_line_follower(now)

    # -------------------------------------------------------
    # Motors langsam an Zielgeschwindigkeit angleichen
    # -------------------------------------------------------

    update_motors(now)


    machine.idle()