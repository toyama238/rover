import network
import socket
import time
import gc
import machine

_ap = None
_server = None
_dns_server = None
_dns_queries = 0
_last_command = None
_current_state = 0
_current_distance = 0
_last_received_command = "none"
_loop_us = None
_loop_max_us = None


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
    <p class="subtitle">Roboter Steuerung</p>

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
        <div class="perf-note">Loop-Anteil = Loop-Laufzeit / (Loop-Laufzeit + 5 ms Sleep).
            Keine echte CPU-Auslastung: WLAN-/FreeRTOS-Tasks sind nicht enthalten.</div>
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


def set_loop_time(duration_us):
    # Vom Hauptprogramm am Ende jedes Schleifendurchlaufs aufrufen.
    # Misst die Python-Hauptschleife, NICHT die gesamte CPU-Auslastung.
    global _loop_us, _loop_max_us
    _loop_us = int(duration_us)
    if _loop_max_us is None or _loop_us > _loop_max_us:
        _loop_max_us = _loop_us


def set_state(state):
    global _current_state
    _current_state = state


def set_distance(distance):
    global _current_distance
    _current_distance = distance / 10


def check_for_running():
    return _server is not None


# Lokaler DNS-Responder fuer rover.move (UDP 53).
# Beantwortet nur IPv4-A-Anfragen fuer diesen Namen.
def _dns_update():
    global _dns_queries
    if _dns_server is None:
        return
    try:
        request, address = _dns_server.recvfrom(512)
    except OSError:
        return  # Kein DNS-Paket vorhanden

    try:
        if len(request) < 17 or request[2] & 0x80:
            return  # Zu kurz oder bereits eine DNS-Antwort
        if request[4:6] != b"\x00\x01":
            return  # Genau eine DNS-Frage erwartet

        pos = 12
        labels = []
        while pos < len(request):
            n = request[pos]
            pos += 1
            if n == 0:
                break
            if n > 63 or pos + n > len(request):
                return
            labels.append(request[pos:pos+n].decode().lower())
            pos += n
        else:
            return

        if pos + 4 > len(request):
            return
        qtype = request[pos:pos+2]
        qclass = request[pos+2:pos+4]
        question = request[12:pos+4]
        name = ".".join(labels)
        is_ours = name == "rover.move" and qclass == b"\x00\x01"
        if not is_ours:
            return  # Andere Domains nicht beeinflussen

        # Antwort mit IPv4-Adresse, falls A-Record angefragt wird.
        if qtype == b"\x00\x01":
            ip = bytes(int(x) for x in _ap.ifconfig()[0].split("."))
            flags = b"\x81\x80"  # Standardantwort ohne Rekursionsserver
            answer_count = b"\x00\x01"
            answer = (b"\xc0\x0c" + b"\x00\x01" + b"\x00\x01"
                      + b"\x00\x00\x00\x1e" + b"\x00\x04" + ip)
        else:
            flags = b"\x81\x80"  # z.B. AAAA: kein Treffer
            answer_count = b"\x00\x00"
            answer = b""

        header = (request[:2] + flags + b"\x00\x01" + answer_count
                  + b"\x00\x00\x00\x00")
        _dns_server.sendto(header + question + answer, address)
        _dns_queries += 1
    except Exception as exc:
        print("DNS error:", exc)


def start_webserver(ssid="Rover1", password="rover123", port=80):
    global _ap, _server, _dns_server

    if _server is not None:
        return

    network.hostname("rover")

    _ap = network.WLAN(network.AP_IF)
    _ap.active(True)
    _ap.config(essid=ssid, password=password)

    while not _ap.active():
        pass

    # DNS-Adresse des AP auf sich selbst setzen. Die Weitergabe durch DHCP
    # ist firmwareabhaengig und muss am Client kontrolliert werden.
    ip = _ap.ifconfig()[0]
    _ap.ifconfig((ip, "255.255.255.0", ip, ip))

    _dns_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _dns_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _dns_server.bind(("0.0.0.0", 53))
    _dns_server.setblocking(False)

    _server = socket.socket()
    _server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server.bind(("0.0.0.0", port))
    _server.listen(5)
    _server.settimeout(0)

    print("Rover WLAN gestartet")
    print("IP:", _ap.ifconfig()[0])
    print("DNS-Name: http://rover.move")
    print("Fallback: http://" + _ap.ifconfig()[0])


def stop_webserver():
    global _ap, _server, _dns_server

    if _dns_server is not None:
        _dns_server.close()
        _dns_server = None

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

    global _last_received_command
    command = _last_command
    _last_command = None
    if command is not None:
        _last_received_command = command
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
    global _last_command, _last_received_command

    _dns_update()

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

        elif "GET /mode_next " in request:
            _last_command = "mode_next"
            send_response(client, "OK", "text/plain")

        elif "GET /mode_prev " in request:
            _last_command = "mode_prev"
            send_response(client, "OK", "text/plain")

        elif "GET /state " in request:
            # Rueckwaertskompatibilitaet fuer alte Clients.
            _last_command = "state"
            send_response(client, "OK", "text/plain")

        elif "GET /status " in request:
            # Nur der MicroPython-Heap, nicht gesamter RAM inkl. WLAN/ESP-IDF.
            heap_free = gc.mem_free()
            heap_used = gc.mem_alloc()
            status = (
                '{"state": ' + str(_current_state)
                + ', "distance": ' + str(_current_distance)
                + ', "pending_command": "' + str(_last_command or "none") + '"'
                + ', "last_command": "' + str(_last_received_command) + '"'
                + ', "uptime_ms": ' + str(time.ticks_ms())
                + ', "heap_free": ' + str(heap_free)
                + ', "heap_used": ' + str(heap_used)
                + ', "cpu_hz": ' + str(machine.freq())
                + ', "loop_us": ' + (str(_loop_us) if _loop_us is not None else 'null')
                + ', "loop_max_us": ' + (str(_loop_max_us) if _loop_max_us is not None else 'null')
                + '}'
            )

            send_response(client, status, "application/json")

        else:
            send_response(client, _html)

    except Exception as e:
        print("Webserver error:", e)

    finally:
        client.close()

