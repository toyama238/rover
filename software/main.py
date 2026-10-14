from machine import Pin, PWM, ADC, I2C
import random
import time
import webserver
import vl53l0x
import rgbLED


# ===========================================================
# 1. KONFIGURATION
# ===========================================================

# Allgemein
state = 0                          # 0 = Manuell, 1 = Hindernis, 2 = Linie
MANUAL_SPEED = 60                  # Prozent
LOOP_PAUSE_MS = 5
DEBUG_INTERVAL_MS = 1000

# Linienfolger
LINE_SPEED = 55
KP = 70
SEARCH_SPEED = 35
MAX_CORRECTION = 75
MAX_SEARCH_TIME = 2000             # ms
LINE_THRESHOLD = 30000
DARK_IS_LOW = True                  # True: Schwarz = kleiner ADC-Wert

# Hindernisvermeidung
OBSTACLE_DISTANCE = 300            # mm
AUTO_SPEED = 60
EXTRA_TURN_TIME = 200              # ms nach Freigabe des Fahrwegs
MAX_TURN_TIME = 5000               # ms, Suchdrehung begrenzen
TOF_INTERVAL_MS = 50               # Sensor-Timing-Budget: 33 ms
TOF_TIMEOUT_MS = 500               # Bei veralteten Messwerten anhalten

# Taster
DEBOUNCE_MS = 50


# ===========================================================
# 2. HARDWARE INITIALISIEREN
# ===========================================================

# ToF-Abstandssensor (VL53L0X) via I2C
# GPIO6 = SDA, GPIO7 = SCL

i2c = I2C(
    0,
    scl=Pin(7),
    sda=Pin(6),
    freq=400000
)

vl53 = vl53l0x.VL53L0X(i2c)
vl53.measurement_timing_budget = 33000
vl53.start_continuous()

# Motoren: je zwei PWM-Ausgänge für die Drehrichtung
left_motor_1 = PWM(Pin(10), freq=200, duty=0)
left_motor_2 = PWM(Pin(8), freq=200, duty=0)
right_motor_1 = PWM(Pin(9), freq=200, duty=0)
right_motor_2 = PWM(Pin(20), freq=200, duty=0)

# Physischer Modus-Taster an GPIO4, gegen GND
button = Pin(4, Pin.IN, Pin.PULL_UP)

# Analoge Linien-Sensoren
line_left = ADC(Pin(2))
line_right = ADC(Pin(3))


# ===========================================================
# 3. LAUFZEITVARIABLEN UND TIMER
# ===========================================================

start_time = time.ticks_ms()

ToF_timer = start_time
debug_timer = start_time

# ToF-Daten in Millimetern
distance = 0
last_valid_tof = None

# Hindernisvermeidung
changing_direction = False
clear_distance_timer = None
turn_start_timer = None
turn_direction = 0
turn_failed = False

# Linienfolger
last_line_direction = 0            # -1 = links, +1 = rechts
line_lost_timer = None

# Entprellung
last_button_state = button.value()
stable_button_state = last_button_state
last_button_time = start_time


# ===========================================================
# 4. MOTOREN
# ===========================================================

def procent_in_PWM(procent):
    """Wandelt 0–100 % in den 10-Bit-PWM-Wert um."""
    procent = max(0, min(100, procent))
    return int(procent * 1023 / 100)


def set_left_motor(procent):
    """Positiv = vorwärts, negativ = rückwärts."""
    if procent >= 0:
        left_motor_2.duty(0)
        left_motor_1.duty(procent_in_PWM(procent))
    else:
        left_motor_1.duty(0)
        left_motor_2.duty(procent_in_PWM(-procent))


def set_right_motor(procent):
    """Positiv = vorwärts, negativ = rückwärts."""
    if procent >= 0:
        right_motor_2.duty(0)
        right_motor_1.duty(procent_in_PWM(procent))
    else:
        right_motor_1.duty(0)
        right_motor_2.duty(procent_in_PWM(-procent))


def drive(left_speed, right_speed):
    """Steuert beide Motoren unabhängig in Prozent (-100 bis +100)."""
    set_left_motor(left_speed)
    set_right_motor(right_speed)


def stop_motors():
    """Setzt beide Motoren auf null."""
    drive(0, 0)


# ===========================================================
# 5. LINIENSENSOREN
# ===========================================================

def isDark(value):
    """Erkennt Schwarz anhand der kalibrierten ADC-Schwelle."""
    if DARK_IS_LOW:
        return value < LINE_THRESHOLD
    else:
        return value > LINE_THRESHOLD


def isLight(value):
    return not isDark(value)


# ===========================================================
# 6. MODUS WECHSELN
# ===========================================================

def set_mode(new_state):
    global state
    global changing_direction, clear_distance_timer
    global turn_start_timer, turn_direction, turn_failed
    global last_line_direction, line_lost_timer

    new_state = new_state % 3

    if new_state == state:
        return

    # Erst Motoren anhalten, dann Modus wechseln
    stop_motors()

    # Laufende Automatiken zurücksetzen
    changing_direction = False
    clear_distance_timer = None
    turn_start_timer = None
    turn_direction = 0
    turn_failed = False

    last_line_direction = 0
    line_lost_timer = None

    state = new_state
    webserver.set_state(state)

    # Modus per RGB-LED anzeigen
    if state == 0:
        rgbLED.set_led("red", 30)
    elif state == 1:
        rgbLED.set_led("blue", 30)
    elif state == 2:
        rgbLED.set_led("yellow", 30)

    print("Mode changed:", state)


# ===========================================================
# 7. START
# ===========================================================

stop_motors()

webserver.start_webserver()
webserver.set_state(state)
webserver.set_distance(0)

rgbLED.boot_rgb_led()
rgbLED.set_led("red", 30)

print("Rover gestartet")


# ===========================================================
# 8. HAUPTSCHLEIFE
# ===========================================================

try:
    while True:
        # Zeit am Schleifenbeginn: Performance-Messung ohne sleep()
        loop_start = time.ticks_us()
        now = time.ticks_ms()

        # ---------------------------------------------------
        # 8.1 Webserver bearbeiten
        # ---------------------------------------------------
        webserver.update_webserver()
        command = webserver.get_command()

        # ---------------------------------------------------
        # 8.2 Moduswechsel per Webseite
        # ---------------------------------------------------
        if command == "mode_next":
            set_mode(state + 1)
        elif command == "mode_prev":
            set_mode(state - 1)
        elif command == "state":
            # Kompatibilität mit älteren Webserver-Versionen
            set_mode(state + 1)

        # ---------------------------------------------------
        # 8.3 Physischen Button entprellen
        # ---------------------------------------------------
        button_state = button.value()

        if button_state != last_button_state:
            last_button_time = now

        # Nur Zustandswechsel nach 50 ms stabilem Pegel akzeptieren
        if time.ticks_diff(now, last_button_time) >= DEBOUNCE_MS:
            if button_state != stable_button_state:
                stable_button_state = button_state

                # Pull-up: 0 bedeutet gedrückt
                if stable_button_state == 0:
                    set_mode(state + 1)

        last_button_state = button_state

        # ---------------------------------------------------
        # 8.4 Abstandssensor aktualisieren
        # ---------------------------------------------------
        if time.ticks_diff(now, ToF_timer) >= TOF_INTERVAL_MS:
            ToF_timer = now

            try:
                reading = vl53.range

                # Plausibilitätsprüfung; Grenzwerte ggf. an Treiber anpassen
                if 0 < reading < 8190:
                    distance = reading
                    last_valid_tof = now
                    webserver.set_distance(distance)
            except Exception as error:
                print("ToF error:", error)

        # Keine Fahrt mit zu altem Abstandswert
        tof_ok = False
        if last_valid_tof is not None:
            if time.ticks_diff(now, last_valid_tof) < TOF_TIMEOUT_MS:
                tof_ok = True

        # ---------------------------------------------------
        # 8.5 Liniensensoren lesen
        # ---------------------------------------------------
        sensLinks = line_left.read_u16()
        sensRechts = line_right.read_u16()

        # ---------------------------------------------------
        # 8.6 STATE 0: Manuelle Steuerung
        # ---------------------------------------------------
        if state == 0:
            if command == "forward":
                drive(MANUAL_SPEED, MANUAL_SPEED)
            elif command == "backward":
                drive(-MANUAL_SPEED, -MANUAL_SPEED)
            elif command == "left":
                drive(-MANUAL_SPEED, MANUAL_SPEED)
            elif command == "right":
                drive(MANUAL_SPEED, -MANUAL_SPEED)
            elif command == "stop":
                stop_motors()

            # Noch kein WLAN-Watchdog: Bei Verbindungsabbruch kann
            # der letzte Fahrbefehl aktiv bleiben.

        # ---------------------------------------------------
        # 8.7 STATE 1: Hindernisvermeidung
        # ---------------------------------------------------
        elif state == 1:
            if turn_failed:
                # Zu lange gedreht: bis zum nächsten Moduswechsel anhalten
                stop_motors()

            elif not tof_ok:
                # Kein aktueller Abstandswert vorhanden
                stop_motors()
                changing_direction = False
                clear_distance_timer = None
                turn_start_timer = None

            else:
                if not changing_direction:
                    if distance <= OBSTACLE_DISTANCE:
                        # Hindernis gefunden -> zufällige Suchrichtung
                        changing_direction = True
                        clear_distance_timer = None
                        turn_start_timer = now

                        if random.randint(0, 1) == 0:
                            turn_direction = -1
                            print("Obstacle: turning left")
                        else:
                            turn_direction = 1
                            print("Obstacle: turning right")
                    else:
                        drive(AUTO_SPEED, AUTO_SPEED)

                if changing_direction:
                    # Drehzeit überwachen
                    if time.ticks_diff(now, turn_start_timer) >= MAX_TURN_TIME:
                        stop_motors()
                        changing_direction = False
                        clear_distance_timer = None
                        turn_failed = True
                        print("Dreh-Timeout: Modus wechseln zum Zurücksetzen")
                    else:
                        # Gespeicherte Drehrichtung weiterfahren
                        if turn_direction == -1:
                            drive(-AUTO_SPEED, AUTO_SPEED)
                        else:
                            drive(AUTO_SPEED, -AUTO_SPEED)

                        if distance > OBSTACLE_DISTANCE:
                            if clear_distance_timer is None:
                                clear_distance_timer = now
                            elif time.ticks_diff(now, clear_distance_timer) >= EXTRA_TURN_TIME:
                                changing_direction = False
                                clear_distance_timer = None
                                drive(AUTO_SPEED, AUTO_SPEED)
                                print("Path clear -> forward")
                        else:
                            clear_distance_timer = None

        # ---------------------------------------------------
        # 8.8 STATE 2: P-Regler mit Liniensuche
        # ---------------------------------------------------
        elif state == 2:
            left_dark = isDark(sensLinks)
            right_dark = isDark(sensRechts)

            if not left_dark and not right_dark:
                # Beide Sensoren Weiß -> mögliche verlorene Linie
                # Funktioniert nur, wenn auf der Linie mindestens ein
                # Sensor normalerweise Schwarz erkennt.
                if line_lost_timer is None:
                    line_lost_timer = now
                    print("Line lost, direction:", last_line_direction)

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
                # Linie erkannt: Proportionalregelung
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
        # 8.9 Performance an Webserver übertragen
        # ---------------------------------------------------
        loop_duration_us = time.ticks_diff(time.ticks_us(), loop_start)
        webserver.set_loop_time(loop_duration_us)

        # ---------------------------------------------------
        # 8.10 Konsolen-Debug (einmal pro Sekunde)
        # ---------------------------------------------------
        if time.ticks_diff(now, debug_timer) >= DEBUG_INTERVAL_MS:
            debug_timer = now

            print(
                "State:", state,
                "| Command:", command,
                "| Distance:", distance, "mm",
                "| Left:", sensLinks,
                "| Right:", sensRechts,
                "| Loop:", loop_duration_us, "us"
            )

        time.sleep_ms(LOOP_PAUSE_MS)

except KeyboardInterrupt:
    print("Programm gestoppt")
finally:
    stop_motors()
