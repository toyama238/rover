import network
import socket
import time
import gc
import machine
import ubinascii
import json

# ------------------------------------------------------------
# Configuration and internal state
# ------------------------------------------------------------

_ap = None
_server = None

_last_command = None
_last_received_command = "none"
_current_state = 0
_current_distance_cm = 0.0
_loop_us = None

# Get a convenient short ID. This is the currently configured STA MAC,
# not necessarily a direct reading of the eFuse factory base MAC.
_station = network.WLAN(network.STA_IF)
_mac = ubinascii.hexlify(_station.config("mac"), ":").decode()
_short_mac = ":".join(_mac.split(":")[3:])
DEFAULT_SSID = "Rover " + _short_mac

# Persistent trim in percentage points: positive = stronger left motor.
# Loaded once at boot; saved only when the user presses +/-.
CALIBRATION_FILE = "rover_calibration.json"
CALIBRATION_MIN = -10
CALIBRATION_MAX = 10
_calibration = 0


def _load_calibration():
    global _calibration
    try:
        with open(CALIBRATION_FILE, "r") as file:
            value = json.load(file).get("trim", 0)
        value = int(value)
        if CALIBRATION_MIN <= value <= CALIBRATION_MAX:
            _calibration = value
    except (OSError, ValueError, TypeError, AttributeError):
        _calibration = 0


def get_calibration():
    """Signed straight-drive correction in percentage points."""
    return _calibration


def _change_calibration(delta):
    """Adjust trim and persist it in flash on each actual change."""
    global _calibration
    new_value = max(CALIBRATION_MIN, min(CALIBRATION_MAX, _calibration + delta))
    if new_value == _calibration:
        return
    # Write before activating the new value, so a failed write is visible.
    try:
        with open(CALIBRATION_FILE, "w") as file:
            json.dump({"trim": new_value}, file)
    except OSError as error:
        print("Calibration save error:", error)
        raise
    _calibration = new_value


_load_calibration()


# ------------------------------------------------------------
# Embedded HTML / CSS / JavaScript
# ------------------------------------------------------------

_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Rover Control</title>

    <style>
        * { box-sizing: border-box; }

        body {
            margin: 0;
            padding: 20px;
            font-family: Arial, sans-serif;
            text-align: center;
            background: #171717;
            color: white;
            user-select: none;
            -webkit-user-select: none;
        }

        h1 {
            margin: 10px 0 5px;
            font-size: 32px;
        }

        h2 {
            margin-top: 5px;
        }

        .subtitle {
            margin-top: 0;
            margin-bottom: 24px;
            color: #aaa;
        }

        .card {
            max-width: 420px;
            margin: 0 auto 20px;
            padding: 20px;
            background: #242424;
            border-radius: 18px;
        }

        #mode-label {
            font-size: 18px;
            margin-bottom: 12px;
        }

        .mode-switch { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
        .mode-arrow { width: 58px; height: 58px; flex-shrink: 0; border: 0;
            border-radius: 12px; background: #3a3a3a; color: white;
            font-size: 28px; cursor: pointer; touch-action: manipulation; }
        .mode-arrow:active { background: #666; }
        #mode-label { flex: 1; margin: 0; }

        .drive-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            grid-template-rows: auto auto auto;
            gap: 12px;
            max-width: 330px;
            margin: 0 auto;
        }

        .drive-button {
            height: 90px;
            border: none;
            border-radius: 18px;
            background: #3b3b3b;
            color: white;
            font-size: 18px;
            font-weight: bold;
            touch-action: none;
            cursor: pointer;
        }

        .drive-button:active {
            background: #666;
            transform: scale(0.96);
        }

        #forward { grid-column: 2; grid-row: 1; }
        #left { grid-column: 1; grid-row: 2; }
        #right { grid-column: 3; grid-row: 2; }
        #backward { grid-column: 2; grid-row: 3; }

        .direction {
            display: block;
            font-size: 25px;
            margin-bottom: 5px;
        }

        #autonomous-panel,
        #line-panel {
            display: none;
        }

        #autonomous-panel p,
        #line-panel p {
            color: #aaa;
        }

        #debug-panel {
            max-width: 420px;
            margin: 12px auto 0;
            padding: 16px;
            text-align: left;
            background: #101010;
            border-radius: 12px;
            font-family: monospace;
            font-size: 14px;
        }

        #debug-panel p {
            margin: 7px 0;
        }

        .debug-key {
            color: #888;
        }
        .cal-row { display: flex; align-items: center; gap: 12px; justify-content: center; }
        .cal-button { width: 70px; height: 58px; border: none; border-radius: 12px;
            background: #3a3a3a; color: #fff; font-size: 29px; font-weight: bold;
            cursor: pointer; touch-action: manipulation; user-select: none; -webkit-user-select: none; }
        .cal-button:active { background: #666; }
        .cal-value { flex: 1; font-size: 30px; font-weight: bold; font-variant-numeric: tabular-nums; }
        .cal-hint { color: #aaa; font-size: 12px; line-height: 1.5; margin: 12px 0 0; }
        .perf-header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
        .perf-header h2 { margin: 0; font-size: 20px; }
        .perf-subtitle { color: #aaa; font-size: 12px; text-align: left; margin: 9px 0 16px; }
        .perf-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; text-align: left; }
        .perf-tile { padding: 14px; border-radius: 12px; background: #303030; min-width: 0; }
        .perf-label { color: #aaa; font-size: 12px; margin-bottom: 7px; }
        .perf-value { font-size: 23px; font-weight: bold; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
        .perf-unit { font-size: 12px; color: #aaa; font-weight: normal; }
        .perf-meter { height: 8px; border-radius: 8px; margin-top: 12px; background: #505050; overflow: hidden; }
        .perf-meter-fill { height: 100%; width: 0; background: #43be9b; transition: width .2s; }
        .perf-detail { font-size: 12px; color: #aaa; margin-top: 12px; text-align: left; line-height: 1.5; }
        .perf-note { color: #aaa; font-size: 11px; line-height: 1.5; text-align: left; margin-top: 12px; }
        button, .drive-button, .mode-arrow { -webkit-user-select: none; user-select: none; -webkit-touch-callout: none; }


        @media (max-width: 480px) {
            body { padding: 14px; }
            h1 { font-size: 28px; }
            .card { padding: 16px; }
            .drive-button { height: 82px; }
        }
    </style>
</head>

<body>

    <h1>Rover</h1>

    <div class="card">
        <div class="mode-switch">
            <button class="mode-arrow" onclick="changeMode(-1)" aria-label="Vorheriger Modus">&#8592;</button>
            <div id="mode-label">Modus:<br><strong id="mode-name">Manuell</strong></div>
            <button class="mode-arrow" onclick="changeMode(1)" aria-label="Naechster Modus">&#8594;</button>
        </div>
    </div>

    <div id="control-panel" class="card">
        <h2>Steuerung</h2>

        <div class="drive-grid">
            <button id="forward" class="drive-button"
                onpointerdown="driveStart('forward')"
                onpointerup="driveStop()"
                onpointercancel="driveStop()"
                onpointerleave="driveStop()">
                <span class="direction">^</span>
                Vorwaerts
            </button>

            <button id="left" class="drive-button"
                onpointerdown="driveStart('left')"
                onpointerup="driveStop()"
                onpointercancel="driveStop()"
                onpointerleave="driveStop()">
                <span class="direction">&lt;</span>
                Links
            </button>

            <button id="right" class="drive-button"
                onpointerdown="driveStart('right')"
                onpointerup="driveStop()"
                onpointercancel="driveStop()"
                onpointerleave="driveStop()">
                <span class="direction">&gt;</span>
                Rechts
            </button>

            <button id="backward" class="drive-button"
                onpointerdown="driveStart('backward')"
                onpointerup="driveStop()"
                onpointercancel="driveStop()"
                onpointerleave="driveStop()">
                <span class="direction">v</span>
                Rueckwaerts
            </button>
        </div>
    </div>

    <div id="autonomous-panel" class="card">
        <h2>Hindernisvermeidung</h2>
        <p>Der Rover faehrt selbststaendig.</p>
        <p>Der Abstandssensor erkennt Hindernisse.</p>
    </div>

    <div id="line-panel" class="card">
        <h2>Linienfolger</h2>
        <p>Der Rover folgt selbststaendig einer Linie.</p>
        <p>Die manuelle Steuerung ist deaktiviert.</p>
    </div>

    <!-- Persistent motor trim, only for straight driving -->
    <section id="calibration-panel" class="card">
        <h2>Motor-Kalibrierung</h2>
        <div class="cal-row">
            <button class="cal-button" onclick="changeCalibration(-1)" aria-label="Weniger">&minus;</button>
            <div class="cal-value" id="cal-value">0</div>
            <button class="cal-button" onclick="changeCalibration(1)" aria-label="Mehr">+</button>
        </div>
        <p class="cal-hint">-10 bis +10</p>
    </section>

    <section id="performance-panel" class="card">
        <div class="perf-header">
            <h2>ESP32-C3 Performance</h2>
            <span id="perf-health" style="font-size:12px;color:#aaa">Warte auf Daten</span>
        </div>
        <p class="perf-subtitle">Live-Messwerte vom Rover · Abfrage alle 200 ms</p>
        <div class="perf-grid">
            <div class="perf-tile">
                <div class="perf-label">MicroPython-Heap</div>
                <div class="perf-value"><span id="perf-ram-percent">--</span><span class="perf-unit"> %</span></div>
                <div class="perf-meter"><div class="perf-meter-fill" id="perf-ram-bar"></div></div>
            </div>
            <div class="perf-tile">
                <div class="perf-label">Loop-Anteil (Schätzung)</div>
                <div class="perf-value"><span id="perf-loop-percent">--</span><span class="perf-unit"> %</span></div>
                <div class="perf-meter"><div class="perf-meter-fill" id="perf-loop-bar"></div></div>
            </div>
            <div class="perf-tile">
                <div class="perf-label">Letzter Loop</div>
                <div class="perf-value"><span id="perf-loop-ms">--</span><span class="perf-unit"> ms</span></div>
            </div>
            <div class="perf-tile">
                <div class="perf-label">CPU-Takt</div>
                <div class="perf-value"><span id="perf-cpu-mhz">--</span><span class="perf-unit"> MHz</span></div>
            </div>
        </div>
        <div class="perf-note">Loop gibt an, wie lange ein Durchlauf des codes braucht. Loop-Anteil schätzt daraus die CPU-Auslastung.</div>
    </section>

    <div id="debug-panel">
        <h2>Live-Debug</h2>
        <p><span class="debug-key">State:</span> <span id="debug-state">0</span></p>
        <p><span class="debug-key">Mode:</span> <span id="debug-mode">Manuell</span></p>
        <p><span class="debug-key">Distance:</span> <span id="debug-distance">0</span> cm</p>
        <p><span class="debug-key">Letzter Befehl:</span> <span id="debug-last">none</span></p>
        <p><span class="debug-key">Ausstehend:</span> <span id="debug-pending">none</span></p>
        <p><span class="debug-key">Zuletzt gesendet:</span> <span id="debug-command">none</span></p>
        <p><span class="debug-key">Uptime:</span> <span id="debug-uptime">--</span> ms</p>
        <p><span class="debug-key">Zuletzt synchronisiert:</span> <span id="debug-synced">--</span></p>
        <p><span class="debug-key">Status:</span> <span id="debug-status">verbinde...</span></p>
        <p><span class="debug-key">Antwortzeit:</span> <span id="debug-latency">--</span> ms</p>
    </div>

    <script>
        let currentState = 0;
        let polling = false;
        let modeRequestPending = false;
        const modes = ["Manuell", "Hindernisvermeidung", "Linienfolger"];
        const debug = (id, value) => { document.getElementById(id).textContent = value; };

        function driveStart(command) {
            if (currentState === 0) send(command);
        }
        function driveStop() {
            if (currentState === 0) send("stop");
        }
        async function send(command) {
            debug("debug-command", command);
            try {
                const response = await fetch("/" + command, {cache: "no-store"});
                if (!response.ok) throw Error("HTTP " + response.status);
            } catch(e) {
                debug("debug-status", "Befehl fehlgeschlagen: " + e.message);
            }
        }
        async function changeMode(direction) {
            if (modeRequestPending) return;
            modeRequestPending = true;
            const target = (currentState + direction + 3) % 3;
            const command = direction > 0 ? "mode_next" : "mode_prev";
            debug("debug-command", command);
            try {
                const response = await fetch("/" + command, {cache: "no-store"});
                if (!response.ok) throw Error("HTTP " + response.status);
                // Der ESP bestaetigt den tatsaechlichen Zustand ueber /status.
                // Daher hier kein lokales currentState++.
                debug("debug-status", "Moduswechsel angefordert: " + modes[target]);
            } catch(e) {
                debug("debug-status", "Moduswechsel fehlgeschlagen: " + e.message);
            } finally {
                modeRequestPending = false;
            }
        }
        let calibrationRequestPending = false;
        async function changeCalibration(delta) {
            if (calibrationRequestPending) return;
            calibrationRequestPending = true;
            const path = delta > 0 ? "/calibration/plus" : "/calibration/minus";
            try {
                const response = await fetch(path, {cache: "no-store"});
                if (!response.ok) throw Error("HTTP " + response.status);
                const data = await response.json();
                debug("cal-value", (data.calibration > 0 ? "+" : "") + data.calibration);
            } catch (error) {
                debug("debug-status", "Kalibrierung fehlgeschlagen: " + error.message);
            } finally {
                calibrationRequestPending = false;
            }
        }
        function updateUI() {
            const state = Number(currentState);
            debug("debug-state", state);
            debug("debug-mode", modes[state] || "Unbekannt");
            debug("mode-name", modes[state] || "Unbekannt");
            document.getElementById("control-panel").style.display = state === 0 ? "block" : "none";
            document.getElementById("autonomous-panel").style.display = state === 1 ? "block" : "none";
            document.getElementById("line-panel").style.display = state === 2 ? "block" : "none";
        }
        async function syncStatus() {
            if (polling) return; // keine ueberlappenden HTTP-Anfragen
            polling = true;
            const started = performance.now();
            try {
                const response = await fetch("/status", {cache: "no-store"});
                if (!response.ok) throw Error("HTTP " + response.status);
                const data = await response.json();
                currentState = Number(data.state);
                debug("cal-value", (data.calibration > 0 ? "+" : "") + data.calibration);
                debug("debug-distance", Number(data.distance).toFixed(1));
                debug("debug-pending", data.pending_command || "none");
                debug("debug-last", data.last_command || "none");
                debug("debug-uptime", data.uptime_ms);
                debug("debug-latency", Math.round(performance.now() - started));
                debug("debug-synced", new Date().toLocaleTimeString());
                debug("debug-status", "verbunden");
                updatePerformance(data);
                updateUI();
            } catch(e) {
                debug("debug-status", "Synchronisierung fehlgeschlagen: " + e.message);
                debug("perf-health", "Verbindung unterbrochen");
            } finally {
                polling = false;
            }
        }
        function updatePerformance(data) {
            const used = Number(data.heap_used);
            const free = Number(data.heap_free);
            const total = used + free;
            const pct = total > 0 ? used / total * 100 : 0;
            debug("perf-ram-percent", pct.toFixed(1));
            document.getElementById("perf-ram-bar").style.width = pct.toFixed(1) + "%";
            debug("perf-cpu-mhz", Number(data.cpu_hz / 1000000).toFixed(0));
            debug("perf-loop-ms", data.loop_us == null ? "--" : (data.loop_us / 1000).toFixed(2));
            // Naeherung fuer den Anteil der Python-Hauptschleife am Loop-Zyklus.
            // Die main.py schlaeft am Ende jedes Durchlaufs 5 ms.
            if (data.loop_us == null) {
                debug("perf-loop-percent", "--");
                document.getElementById("perf-loop-bar").style.width = "0%";
            } else {
                const loopMs = Math.max(0, Number(data.loop_us) / 1000);
                const loopShare = 100 * loopMs / (loopMs + 5);
                debug("perf-loop-percent", loopShare.toFixed(1));
                document.getElementById("perf-loop-bar").style.width = loopShare.toFixed(1) + "%";
            }
            debug("perf-health", "Live");
        }
        updateUI();
        syncStatus();
        setInterval(syncStatus, 200);
    </script>

</body>
</html>
"""

# Preparing the static response once avoids repeatedly allocating the page.
_html_bytes = _html.encode("utf-8")


# ------------------------------------------------------------
# Public API: data supplied by main.py
# ------------------------------------------------------------


def set_state(state):
    """Update the mode visible to the browser: 0, 1 or 2."""
    global _current_state
    _current_state = int(state)


def set_distance(distance_mm):
    """Accept the ToF value in millimetres; display it in centimetres."""
    global _current_distance_cm
    _current_distance_cm = distance_mm / 10


def set_loop_time(duration_us):
    """Execution time of a main.py loop iteration, excluding sleep_ms()."""
    global _loop_us
    _loop_us = int(duration_us)


def get_command():
    """Read and consume the most recent browser command."""
    global _last_command, _last_received_command

    command = _last_command
    _last_command = None

    if command is not None:
        _last_received_command = command

    return command


def get_ip():
    """Return the access point IP, or None when Wi-Fi is stopped."""
    if _ap is None:
        return None
    return _ap.ifconfig()[0]


def check_for_running():
    """Return True when the HTTP server has been started."""
    return _server is not None


# ------------------------------------------------------------
# Startup and shutdown
# ------------------------------------------------------------


def start_webserver(ssid=None, password="rover123", port=80):
    """Start Wi-Fi AP and HTTP server (no DNS server)."""
    global _ap, _server

    if _server is not None:
        return

    if ssid is None:
        ssid = DEFAULT_SSID

    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=ssid, password=password)

    server = None
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", port))
        server.listen(5)
        server.setblocking(False)
    except Exception:
        if server is not None:
            server.close()
        ap.active(False)
        raise

    _ap = ap
    _server = server

    print("Rover WLAN gestartet:", ssid)
    print("MAC (STA):", _mac)
    print("Webseite: http://" + get_ip())


def stop_webserver():
    """Close the HTTP server and disable the access point."""
    global _ap, _server

    if _server is not None:
        _server.close()
        _server = None

    if _ap is not None:
        _ap.active(False)
        _ap = None


# ------------------------------------------------------------
# HTTP helpers
# ------------------------------------------------------------


def _send_response(client, body, content_type="text/plain", status=200):
    """Send a complete response to a connected client."""
    if isinstance(body, str):
        body = body.encode("utf-8")

    header = (
        (
            "HTTP/1.1 200 OK\r\n"
            if status == 200
            else "HTTP/1.1 500 Internal Server Error\r\n"
        )
        + "Content-Type: "
        + content_type
        + "; charset=UTF-8\r\n"
        "Content-Length: " + str(len(body)) + "\r\n"
        "Cache-Control: no-store\r\n"
        "Connection: close\r\n"
        "\r\n"
    )

    # MicroPython socket.write() sends the entire buffer for blocking sockets.
    client.write(header.encode("utf-8"))
    client.write(body)


def _status():
    """Collect the values used by the status and performance panels."""
    return {
        "state": _current_state,
        "calibration": _calibration,
        "distance": _current_distance_cm,
        "pending_command": _last_command or "none",
        "last_command": _last_received_command,
        "uptime_ms": time.ticks_ms(),
        "heap_free": gc.mem_free(),
        "heap_used": gc.mem_alloc(),
        "cpu_hz": machine.freq(),
        "loop_us": _loop_us,
    }


# ------------------------------------------------------------
# Poll once per main loop. Do not put a while True here.
# ------------------------------------------------------------


def update_webserver():
    """Handle at most one pending HTTP request per call."""
    global _last_command

    if _server is None:
        return

    try:
        client, _address = _server.accept()
    except OSError:
        # No incoming request: immediately return to the motor control loop.
        return

    try:
        # Avoid hanging forever if a client opens a connection but sends no data.
        client.settimeout(0.1)
        request = client.recv(1024)
        if not request:
            return

        # Parse the requested path from the first HTTP request line.
        request_line = request.split(b"\r\n", 1)[0]
        parts = request_line.split(b" ")
        if len(parts) < 2 or parts[0] != b"GET":
            return
        path = parts[1]

        if path == b"/status":
            _send_response(client, json.dumps(_status()), "application/json")

        elif path == b"/calibration/plus" or path == b"/calibration/minus":
            # Save to flash only on user interaction, never on 200 ms polling.
            try:
                _change_calibration(1 if path == b"/calibration/plus" else -1)
                _send_response(
                    client,
                    json.dumps({"calibration": _calibration}),
                    "application/json",
                )
            except OSError:
                _send_response(
                    client, '{"error":"flash save failed"}', "application/json", 500
                )

        elif path in (
            b"/forward",
            b"/backward",
            b"/left",
            b"/right",
            b"/stop",
            b"/mode_next",
            b"/mode_prev",
            b"/state",
        ):
            # main.py receives this command in its next get_command() call.
            _last_command = path[1:].decode()
            _send_response(client, "OK")

        elif path == b"/" or path.startswith(b"/?"):
            _send_response(client, _html_bytes, "text/html")

        else:
            _send_response(client, "Not found")

    except Exception as exc:
        print("HTTP error:", exc)

    finally:
        client.close()
