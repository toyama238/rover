import network
import socket

_ap = None
_server = None
_last_command = None
_current_state = 0
_current_distance = 0

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

        #state-button,
        #debug-toggle {
            width: 100%;
            max-width: 420px;
            border: none;
            border-radius: 12px;
            background: #3a3a3a;
            color: white;
            cursor: pointer;
        }

        #state-button {
            height: 60px;
            font-size: 18px;
            font-weight: bold;
        }

        #debug-toggle {
            height: 48px;
            font-size: 15px;
        }

        #state-button:active,
        #debug-toggle:active {
            background: #555;
            transform: scale(0.98);
        }

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
        #line-panel,
        #debug-panel {
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
    <p class="subtitle">Roboter Steuerung</p>

    <div class="card">
        <div id="mode-label">
            Modus: <strong id="mode-name">Manuell</strong>
        </div>

        <button id="state-button" onclick="send('state')">
            Zu Hindernisvermeidung
        </button>
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

    <button id="debug-toggle" onclick="toggleDebug()">
        Debug anzeigen
    </button>

    <div id="debug-panel">
        <p><span class="debug-key">Command:</span>
            <span id="debug-command">none</span></p>

        <p><span class="debug-key">State:</span>
            <span id="debug-state">0</span></p>

        <p><span class="debug-key">Mode:</span>
            <span id="debug-mode">Manual</span></p>

        <p><span class="debug-key">Distance:</span>
            <span id="debug-distance">0</span> cm</p>

        <p><span class="debug-key">Status:</span>
            <span id="debug-status">connected</span></p>
    </div>

    <script>
        let currentState = 0;
        let debugVisible = false;

        function driveStart(command) {
            if (currentState === 0) {
                send(command);
            }
        }

        function driveStop() {
            if (currentState === 0) {
                send("stop");
            }
        }

        function send(command) {
            document.getElementById("debug-command").innerText = command;
            document.getElementById("debug-status").innerText = "sending...";

            if (command === "state") {
                currentState = (currentState + 1) % 3;
                updateUI();
            }

            fetch("/" + command)
                .then(response => {
                    document.getElementById("debug-status").innerText =
                        response.ok ? "connected" : "HTTP error";
                })
                .catch(() => {
                    document.getElementById("debug-status").innerText =
                        "connection lost";
                });
        }

        function updateUI() {
            document.getElementById("debug-state").innerText = currentState;

            const control = document.getElementById("control-panel");
            const autonomous = document.getElementById("autonomous-panel");
            const line = document.getElementById("line-panel");
            const mode = document.getElementById("mode-name");
            const debugMode = document.getElementById("debug-mode");
            const stateButton = document.getElementById("state-button");

            control.style.display = "none";
            autonomous.style.display = "none";
            line.style.display = "none";

            if (currentState === 0) {
                control.style.display = "block";
                mode.innerText = "Manuell";
                debugMode.innerText = "Manual";
                stateButton.innerText = "Zu Hindernisvermeidung";
            }
            else if (currentState === 1) {
                autonomous.style.display = "block";
                mode.innerText = "Hindernisvermeidung";
                debugMode.innerText = "Obstacle Avoidance";
                stateButton.innerText = "Zum Linienfolger";
            }
            else {
                line.style.display = "block";
                mode.innerText = "Linienfolger";
                debugMode.innerText = "Line Following";
                stateButton.innerText = "Zur manuellen Steuerung";
            }
        }

        function toggleDebug() {
            debugVisible = !debugVisible;

            document.getElementById("debug-panel").style.display =
                debugVisible ? "block" : "none";

            document.getElementById("debug-toggle").innerText =
                debugVisible ? "Debug ausblenden" : "Debug anzeigen";
        }

        function syncStatus() {
            fetch("/status")
                .then(response => response.json())
                .then(data => {
                    currentState = data.state;

                    document.getElementById("debug-distance").innerText =
                        Number(data.distance).toFixed(1);

                    document.getElementById("debug-status").innerText =
                        "connected";

                    updateUI();
                })
                .catch(() => {
                    document.getElementById("debug-status").innerText =
                        "sync failed";
                });
        }

        syncStatus();
        setInterval(syncStatus, 200);
        updateUI();
    </script>

</body>
</html>
"""


def set_state(state):
    global _current_state
    _current_state = state


def set_distance(distance):
    global _current_distance
    _current_distance = distance / 10


def check_for_running():
    return _server is not None


def start_webserver(ssid="Rover", password="rover123", port=80):
    global _ap, _server

    if _server is not None:
        return

    network.hostname("rover")

    _ap = network.WLAN(network.AP_IF)
    _ap.active(True)
    _ap.config(essid=ssid, password=password)

    while not _ap.active():
        pass

    _server = socket.socket()
    _server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server.bind(("0.0.0.0", port))
    _server.listen(5)
    _server.settimeout(0)

    print("Rover WLAN gestartet")
    print("IP:", _ap.ifconfig()[0])
    print("Versuche: http://rover.local")


def stop_webserver():
    global _ap, _server

    if _server is not None:
        _server.close()
        _server = None

    if _ap is not None:
        _ap.active(False)
        _ap = None


def get_ip():
    if _ap is None:
        return None

    return _ap.ifconfig()[0]


def get_command():
    global _last_command

    command = _last_command
    _last_command = None
    return command


def send_response(client, content, content_type="text/html"):
    response = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: " + content_type + "; charset=UTF-8\r\n"
        "Cache-Control: no-cache\r\n"
        "Connection: close\r\n"
        "\r\n"
        + content
    )

    client.send(response)


def update_webserver():
    global _last_command

    if _server is None:
        return

    try:
        client, address = _server.accept()
    except OSError:
        return

    try:
        request = client.recv(1024).decode()

        if "GET /forward " in request:
            _last_command = "forward"
            send_response(client, "OK", "text/plain")

        elif "GET /backward " in request:
            _last_command = "backward"
            send_response(client, "OK", "text/plain")

        elif "GET /left " in request:
            _last_command = "left"
            send_response(client, "OK", "text/plain")

        elif "GET /right " in request:
            _last_command = "right"
            send_response(client, "OK", "text/plain")

        elif "GET /stop " in request:
            _last_command = "stop"
            send_response(client, "OK", "text/plain")

        elif "GET /state " in request:
            _last_command = "state"
            send_response(client, "OK", "text/plain")

        elif "GET /status " in request:
            status = (
                '{"state": ' + str(_current_state)
                + ', "distance": ' + str(_current_distance)
                + '}'
            )

            send_response(client, status, "application/json")

        else:
            send_response(client, _html)

    except Exception as e:
        print("Webserver error:", e)

    finally:
        client.close()