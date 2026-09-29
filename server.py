import json
import os
import shutil
import socket
import secrets
import subprocess
import io
import threading
import urllib.request
from pathlib import Path
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import pyautogui
from PIL import Image

pyautogui.FAILSAFE = False

HOST = "0.0.0.0"
PORT = 8765
TOKEN = secrets.token_urlsafe(12)

HTML = """<!doctype html>
<html lang="en">
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>KIA Ultimate PC Controller</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
body { background: #070d14; color: #d4f7ff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 14px; }
.wrap { max-width: 600px; margin: 0 auto; padding: 12px; }

/* Tabs */
.tabs { display: flex; gap: 6px; margin-bottom: 12px; overflow-x: auto; padding-bottom: 4px; }
.tab-btn { flex: 1; min-width: 85px; padding: 10px 6px; background: #0c1a24; border: 1px solid #163e50; border-radius: 8px; color: #72dbec; font-size: 12px; font-weight: bold; cursor: pointer; text-align: center; }
.tab-btn.active { background: #124b63; color: #fff; border-color: #38bdf8; }

.tab-content { display: none; }
.tab-content.active { display: block; }

.card { background: #0b1622; border: 1px solid #163e50; border-radius: 12px; padding: 12px; margin-bottom: 12px; }
.card-title { font-size: 13px; color: #38bdf8; font-weight: bold; text-transform: uppercase; margin-bottom: 8px; }

.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; }
.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }

button { padding: 10px; border-radius: 8px; border: 1px solid #18526b; background: #0c2636; color: #a5f3fc; font-weight: 600; cursor: pointer; font-size: 13px; }
button:active { background: #195e7d; }
button.danger { border-color: #882b35; background: #280f13; color: #fca5a5; }
button.warn { border-color: #b58900; background: #292004; color: #fde047; }
button.success { border-color: #1e7040; background: #0d2c19; color: #86efac; }

#trackpad { width: 100%; height: 210px; background: #050b11; border: 2px dashed #1b495c; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: #41758c; font-weight: bold; user-select: none; touch-action: none; }

.file-list { max-height: 280px; overflow-y: auto; background: #060e17; border: 1px solid #123140; border-radius: 8px; margin: 8px 0; }
.file-item { display: flex; justify-content: space-between; align-items: center; padding: 9px 10px; border-bottom: 1px solid #0d212c; font-size: 13px; }
.file-item:last-child { border-bottom: none; }
.file-info { display: flex; align-items: center; gap: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-actions { display: flex; gap: 4px; }
.file-actions button { padding: 4px 8px; font-size: 11px; }

input, textarea { width: 100%; padding: 9px; background: #060e17; border: 1px solid #163e50; border-radius: 8px; color: #d4f7ff; font-size: 13px; margin-bottom: 8px; }
#status { font-size: 12px; color: #38bdf8; white-space: pre-wrap; word-break: break-all; }
#screen-preview { width: 100%; border-radius: 8px; border: 1px solid #163e50; display: block; margin-top: 8px; }

.info-box { background: #06111a; border: 1px solid #163e50; border-radius: 8px; padding: 10px; font-size: 13px; line-height: 1.6; margin-bottom: 8px; }
</style>
</head>
<body>
<div class="wrap">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
    <h2 style="color:#38bdf8; font-size:18px;">KIA REMOTE HUB</h2>
    <button style="padding:4px 8px; font-size:11px;" onclick="refreshScreen()">🔄 Live View</button>
  </div>

  <div class="card" style="padding:8px 12px;"><div id="status">Ready</div></div>

  <!-- Tab Navigation -->
  <div class="tabs">
    <div class="tab-btn active" onclick="switchTab('tab-find')">📍 Find My PC</div>
    <div class="tab-btn" onclick="switchTab('tab-remote')">🖱️ Mouse/Key</div>
    <div class="tab-btn" onclick="switchTab('tab-files'); loadFiles();">📁 Files & IDE</div>
    <div class="tab-btn" onclick="switchTab('tab-terminal')">💻 Terminal</div>
    <div class="tab-btn" onclick="switchTab('tab-apps')">🚀 Apps & Power</div>
  </div>

  <!-- TAB 0: FIND MY PC & LOCATION -->
  <div id="tab-find" class="tab-content active">
    <div class="card">
      <div class="card-title">Device Locator & Ring Alarm</div>
      <p style="font-size:12px; color:#7dd3fc; margin-bottom:10px;">
        Ghar ya office me PC na milne par high-volume siren bajayein ya online geolocation check karein.
      </p>
      <div class="grid-2">
        <button class="danger" style="font-size:14px; padding:14px;" onclick="cmd('ring_alarm')">🔊 Ring Alarm (Full Vol)</button>
        <button class="success" style="font-size:14px; padding:14px;" onclick="fetchLocation()">📍 Track Location</button>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Live Geolocation Details</div>
      <div id="locDetails" class="info-box">Press "Track Location" to fetch current PC coordinates.</div>
      <button id="mapsBtn" style="display:none; width:100%;" class="warn" onclick="openMaps()">🗺️ Open in Google Maps</button>
    </div>
  </div>

  <!-- TAB 1: REMOTE (MOUSE & KEYBOARD) -->
  <div id="tab-remote" class="tab-content">
    <div class="card">
      <div class="card-title">Mobile Trackpad</div>
      <div id="trackpad">Drag to Move | Tap to Click</div>
      <div class="grid-3" style="margin-top:8px;">
        <button onclick="mouseAction('left_click')">Left Click</button>
        <button onclick="mouseAction('right_click')">Right Click</button>
        <button onclick="mouseAction('double_click')">Double Click</button>
      </div>
      <div class="grid-2" style="margin-top:6px;">
        <button onclick="mouseAction('scroll_up')">📜 Scroll Up</button>
        <button onclick="mouseAction('scroll_down')">📜 Scroll Down</button>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Virtual Keyboard</div>
      <div style="display:flex; gap:6px;">
        <input type="text" id="typeInput" placeholder="Type text to send to PC...">
        <button onclick="sendText()" style="width:75px;">Send</button>
      </div>
      <div class="grid-4">
        <button onclick="keyPress('enter')">Enter</button>
        <button onclick="keyPress('backspace')">Backspace</button>
        <button onclick="keyPress('space')">Space</button>
        <button onclick="keyPress('esc')">Esc</button>
        <button onclick="hotkey(['ctrl', 'c'])">Ctrl+C</button>
        <button onclick="hotkey(['ctrl', 'v'])">Ctrl+V</button>
        <button onclick="hotkey(['win', 'd'])">Desktop</button>
        <button onclick="hotkey(['alt', 'tab'])">Alt+Tab</button>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Live Screen Snapshot</div>
      <img id="screen-preview" src="" alt="Screen Preview" style="display:none;">
    </div>
  </div>

  <!-- TAB 2: FILES & VS CODE -->
  <div id="tab-files" class="tab-content">
    <div class="card">
      <div class="card-title">File Explorer & Manager</div>
      <div style="display:flex; gap:6px; margin-bottom:6px;">
        <input type="text" id="currentPath" value="" readonly style="margin-bottom:0;">
        <button onclick="goUpDir()" style="width:65px;">⬆️ Up</button>
      </div>
      <div class="file-list" id="fileListContainer">Loading files...</div>

      <div class="grid-2" style="margin-top:8px;">
        <button class="success" onclick="promptCreateFolder()">📁 New Folder</button>
        <button class="success" onclick="promptCreateFile()">📄 New File</button>
      </div>
    </div>
  </div>

  <!-- TAB 3: TERMINAL -->
  <div id="tab-terminal" class="tab-content">
    <div class="card">
      <div class="card-title">Command Prompt / PowerShell</div>
      <textarea id="terminalInput" rows="2" placeholder="e.g. dir, ipconfig, python main.py"></textarea>
      <button class="success" onclick="runCommand()" style="width:100%; margin-bottom:8px;">⚡ Execute Command</button>
      <textarea id="terminalOutput" rows="8" readonly placeholder="Output will appear here..." style="font-family:monospace; font-size:12px;"></textarea>
    </div>
  </div>

  <!-- TAB 4: APPS & POWER -->
  <div id="tab-apps" class="tab-content">
    <div class="card">
      <div class="card-title">Quick Applications</div>
      <div class="grid-2">
        <button onclick="cmd('open_vscode')">💻 Open VS Code</button>
        <button onclick="cmd('open_chrome')">🌐 Google Chrome</button>
        <button onclick="cmd('open_explorer')">📁 File Explorer</button>
        <button onclick="cmd('open_taskmgr')">📊 Task Manager</button>
        <button onclick="cmd('open_notepad')">📝 Notepad</button>
        <button onclick="cmd('open_calc')">🧮 Calculator</button>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Audio & Media</div>
      <div class="grid-3">
        <button onclick="cmd('media_prev')">⏮️ Prev</button>
        <button onclick="cmd('media_play_pause')">⏯️ Play</button>
        <button onclick="cmd('media_next')">⏭️ Next</button>
        <button onclick="cmd('volume_down')">🔉 Vol -</button>
        <button onclick="cmd('mute')">🔇 Mute</button>
        <button onclick="cmd('volume_up')">🔊 Vol +</button>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Power Control</div>
      <div class="grid-2">
        <button onclick="cmd('lock')">🔒 Lock PC</button>
        <button onclick="cmd('sleep')">💤 Sleep PC</button>
        <button class="danger" onclick="confirmCmd('restart')">↻ Restart</button>
        <button class="danger" onclick="confirmCmd('shutdown')">⏻ Shut Down</button>
      </div>
    </div>
  </div>
</div>

<script>
const token = new URLSearchParams(location.search).get('token');
let currentDir = "";
let currentMapsUrl = "";

function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  event.currentTarget.classList.add('active');
  document.getElementById(tabId).classList.add('active');
}

async function api(path, method="POST", data={}) {
  try {
    const r = await fetch(path + (path.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token), {
      method: method,
      headers: {'Content-Type': 'application/json'},
      body: method === "POST" ? JSON.stringify(data) : null
    });
    return await r.json();
  } catch(e) {
    document.getElementById('status').textContent = 'Error: ' + e;
    return { error: e.message };
  }
}

async function cmd(action) {
  const res = await api('/api/command', 'POST', { action });
  document.getElementById('status').textContent = res.message || res.error || 'Executed';
}

function confirmCmd(a) { if(confirm('Execute: ' + a.toUpperCase() + '?')) cmd(a); }

/* Geolocation Tracking */
async function fetchLocation() {
  document.getElementById('locDetails').innerHTML = "Fetching PC location from network...";
  const res = await api('/api/location', 'GET');
  if (res.ok) {
    document.getElementById('locDetails').innerHTML = `
      <b>City:</b> ${res.city}, ${res.region}<br>
      <b>Country:</b> ${res.country}<br>
      <b>Public IP:</b> ${res.ip}<br>
      <b>Coordinates:</b> ${res.lat}, ${res.lon}
    `;
    currentMapsUrl = res.maps_url;
    document.getElementById('mapsBtn').style.display = 'block';
  } else {
    document.getElementById('locDetails').textContent = "Failed to detect location: " + (res.error || 'Unknown error');
  }
}

function openMaps() {
  if (currentMapsUrl) window.open(currentMapsUrl, '_blank');
}

/* Touchpad */
const tp = document.getElementById('trackpad');
let touchStartX = 0, touchStartY = 0, lastSent = 0;
tp.addEventListener('touchstart', (e) => {
  const t = e.touches[0];
  touchStartX = t.clientX;
  touchStartY = t.clientY;
});
tp.addEventListener('touchmove', (e) => {
  e.preventDefault();
  const now = Date.now();
  if (now - lastSent < 35) return;
  lastSent = now;
  const t = e.touches[0];
  const dx = (t.clientX - touchStartX) * 1.6;
  const dy = (t.clientY - touchStartY) * 1.6;
  touchStartX = t.clientX;
  touchStartY = t.clientY;
  api('/api/mouse', 'POST', { action: 'move', dx, dy });
});

function mouseAction(action) { api('/api/mouse', 'POST', { action }); }
function keyPress(key) { api('/api/keyboard', 'POST', { action: 'press', key }); }
function hotkey(keys) { api('/api/keyboard', 'POST', { action: 'hotkey', keys }); }
function sendText() {
  const el = document.getElementById('typeInput');
  if (!el.value) return;
  api('/api/keyboard', 'POST', { action: 'type', text: el.value });
  el.value = '';
}

function refreshScreen() {
  const img = document.getElementById('screen-preview');
  img.style.display = 'block';
  img.src = '/api/screen?token=' + encodeURIComponent(token) + '&t=' + Date.now();
}

/* File Manager */
async function loadFiles(dir="") {
  const res = await api('/api/files?path=' + encodeURIComponent(dir), 'GET');
  if (res.error) return;
  currentDir = res.current;
  document.getElementById('currentPath').value = currentDir;
  const container = document.getElementById('fileListContainer');
  container.innerHTML = '';

  res.items.forEach(item => {
    const row = document.createElement('div');
    row.className = 'file-item';
    row.innerHTML = `
      <div class="file-info" onclick="${item.is_dir ? `loadFiles('${encodeURIComponent(item.path)}')` : ''}" style="cursor:${item.is_dir ? 'pointer' : 'default'}">
        <span>${item.is_dir ? '📁' : '📄'}</span>
        <span style="${item.is_dir ? 'color:#7dd3fc; font-weight:bold;' : ''}">${item.name}</span>
      </div>
      <div class="file-actions">
        <button onclick="openInVSCode('${encodeURIComponent(item.path)}')">💻 VS Code</button>
        ${!item.is_dir ? `<button onclick="runFile('${encodeURIComponent(item.path)}')">▶ Run</button>` : ''}
        <button onclick="promptMove('${encodeURIComponent(item.path)}')">📦 Move</button>
        <button class="danger" onclick="deleteItem('${encodeURIComponent(item.path)}')">🗑️</button>
      </div>
    `;
    container.appendChild(row);
  });
}

function goUpDir() {
  api('/api/files/parent?path=' + encodeURIComponent(currentDir), 'GET').then(res => {
    if (res.path) loadFiles(res.path);
  });
}

function promptCreateFolder() {
  const name = prompt("New Folder Name:");
  if (name) api('/api/files/action', 'POST', { action: 'mkdir', path: currentDir, name }).then(() => loadFiles(currentDir));
}

function promptCreateFile() {
  const name = prompt("New File Name (e.g. test.py, index.js):");
  if (name) api('/api/files/action', 'POST', { action: 'touch', path: currentDir, name }).then(() => loadFiles(currentDir));
}

function promptMove(sourcePath) {
  const dest = prompt("Enter destination folder path:");
  if (dest) api('/api/files/action', 'POST', { action: 'move', src: decodeURIComponent(sourcePath), dest }).then(() => loadFiles(currentDir));
}

function deleteItem(targetPath) {
  if (confirm("Delete this permanently?")) {
    api('/api/files/action', 'POST', { action: 'delete', path: decodeURIComponent(targetPath) }).then(() => loadFiles(currentDir));
  }
}

function openInVSCode(targetPath) {
  api('/api/files/action', 'POST', { action: 'vscode', path: decodeURIComponent(targetPath) }).then(res => {
    document.getElementById('status').textContent = res.message;
  });
}

function runFile(targetPath) {
  api('/api/files/action', 'POST', { action: 'run', path: decodeURIComponent(targetPath) }).then(res => {
    document.getElementById('status').textContent = res.message;
  });
}

/* Terminal */
async function runCommand() {
  const cmd = document.getElementById('terminalInput').value;
  if (!cmd) return;
  document.getElementById('terminalOutput').value = "Running command...";
  const res = await api('/api/terminal', 'POST', { command: cmd, cwd: currentDir });
  document.getElementById('terminalOutput').value = res.output || res.error || "Done.";
}
</script>
</body>
</html>"""

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()

def get_pc_location():
    """Fetches public IP geolocation for location tracking."""
    try:
        req = urllib.request.Request(
            "http://ip-api.com/json/",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data.get("status") == "success":
                lat = data.get("lat")
                lon = data.get("lon")
                return {
                    "ok": True,
                    "city": data.get("city"),
                    "region": data.get("regionName"),
                    "country": data.get("country"),
                    "ip": data.get("query"),
                    "lat": lat,
                    "lon": lon,
                    "maps_url": f"https://www.google.com/maps?q={lat},{lon}"
                }
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "Unable to resolve geolocation."}

def ring_pc_alarm():
    """Unmutes audio, maximizes volume, and sounds an audible locator siren."""
    def _ring():
        try:
            # Volume 100% karna
            for _ in range(30):
                pyautogui.press("volumeup")
            import winsound
            # Alternating dual frequency siren
            for _ in range(10):
                winsound.Beep(1100, 300)
                winsound.Beep(1700, 300)
        except Exception:
            pass
    threading.Thread(target=_ring, daemon=True).start()
    return "Find My PC: Siren activated at 100% volume."

def execute_system_command(action):
    try:
        if action == "ring_alarm":
            return ring_pc_alarm()
        elif action == "lock":
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=False)
            return "PC locked."
        elif action == "sleep":
            subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                            "Add-Type -AssemblyName System.Windows.Forms; "
                            "[System.Windows.Forms.Application]::SetSuspendState('Suspend',$false,$false)"], check=False)
            return "Sleep activated."
        elif action == "shutdown":
            subprocess.run(["shutdown", "/s", "/t", "5"], check=False)
            return "Shutting down in 5s."
        elif action == "restart":
            subprocess.run(["shutdown", "/r", "/t", "5"], check=False)
            return "Restarting in 5s."
        elif action == "open_vscode":
            subprocess.Popen(["cmd.exe", "/c", "code"], shell=True)
            return "VS Code opened."
        elif action == "open_chrome":
            subprocess.Popen(["cmd.exe", "/c", "start chrome"], shell=True)
            return "Chrome opened."
        elif action == "open_taskmgr":
            subprocess.Popen(["taskmgr.exe"])
            return "Task Manager opened."
        elif action == "open_explorer":
            subprocess.Popen(["explorer.exe"])
            return "Explorer opened."
        elif action == "open_notepad":
            subprocess.Popen(["notepad.exe"])
            return "Notepad opened."
        elif action == "open_calc":
            subprocess.Popen(["calc.exe"])
            return "Calculator opened."
        elif action in ("volume_up", "volume_down", "mute", "media_play_pause", "media_next", "media_prev"):
            key_map = {
                "volume_up": "volumeup", "volume_down": "volumedown", "mute": "volumemute",
                "media_play_pause": "playpause", "media_next": "nexttrack", "media_prev": "prevtrack"
            }
            pyautogui.press(key_map[action])
            return f"Key {action} triggered."
        return "Unknown command."
    except Exception as e:
        return f"Failed: {e}"

class KIAHandler(BaseHTTPRequestHandler):
    def _send_json(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content):
        body = html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        token = q.get("token", [""])[0]

        if token != TOKEN:
            self._send_json(403, {"error": "Unauthorized. Invalid Token."})
            return

        if u.path == "/":
            self._send_html(HTML)
        elif u.path == "/api/location":
            data = get_pc_location()
            self._send_json(200, data)
        elif u.path == "/api/screen":
            img = pyautogui.screenshot()
            img.thumbnail((960, 540))
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=55)
            data = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif u.path == "/api/files":
            raw_path = q.get("path", [""])[0]
            target_path = Path(raw_path) if raw_path else Path.home()
            if not target_path.exists():
                target_path = Path.home()
            
            items = []
            try:
                for entry in sorted(target_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                    items.append({
                        "name": entry.name,
                        "path": str(entry.resolve()),
                        "is_dir": entry.is_dir()
                    })
            except Exception as e:
                items = [{"name": f"Error: {e}", "path": str(target_path), "is_dir": False}]

            self._send_json(200, {"current": str(target_path.resolve()), "items": items})
        elif u.path == "/api/files/parent":
            raw_path = q.get("path", [""])[0]
            current = Path(raw_path) if raw_path else Path.home()
            parent = current.parent if current.parent != current else current
            self._send_json(200, {"path": str(parent.resolve())})
        else:
            self._send_json(404, {"error": "Endpoint not found"})

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        token = q.get("token", [""])[0]

        if token != TOKEN:
            self._send_json(403, {"error": "Unauthorized."})
            return

        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")

        if u.path == "/api/command":
            res = execute_system_command(payload.get("action", ""))
            self._send_json(200, {"message": res})
        elif u.path == "/api/mouse":
            act = payload.get("action")
            if act == "move":
                dx = int(float(payload.get("dx", 0)))
                dy = int(float(payload.get("dy", 0)))
                pyautogui.moveRel(dx, dy)
            elif act == "left_click":
                pyautogui.click()
            elif act == "right_click":
                pyautogui.rightClick()
            elif act == "double_click":
                pyautogui.doubleClick()
            elif act == "scroll_up":
                pyautogui.scroll(250)
            elif act == "scroll_down":
                pyautogui.scroll(-250)
            self._send_json(200, {"ok": True})
        elif u.path == "/api/keyboard":
            act = payload.get("action")
            if act == "type":
                pyautogui.write(payload.get("text", ""), interval=0.01)
            elif act == "press":
                pyautogui.press(payload.get("key", ""))
            elif act == "hotkey":
                pyautogui.hotkey(*payload.get("keys", []))
            self._send_json(200, {"ok": True})
        elif u.path == "/api/files/action":
            act = payload.get("action")
            try:
                if act == "mkdir":
                    base = Path(payload.get("path"))
                    new_dir = base / payload.get("name")
                    new_dir.mkdir(parents=True, exist_ok=True)
                    self._send_json(200, {"message": f"Created folder: {new_dir.name}"})
                elif act == "touch":
                    base = Path(payload.get("path"))
                    new_file = base / payload.get("name")
                    new_file.touch(exist_ok=True)
                    self._send_json(200, {"message": f"Created file: {new_file.name}"})
                elif act == "move":
                    src = Path(payload.get("src"))
                    dest = Path(payload.get("dest"))
                    shutil.move(str(src), str(dest))
                    self._send_json(200, {"message": f"Moved {src.name} to {dest}"})
                elif act == "delete":
                    target = Path(payload.get("path"))
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                    self._send_json(200, {"message": f"Deleted {target.name}"})
                elif act == "vscode":
                    target = payload.get("path")
                    subprocess.Popen(f'code "{target}"', shell=True)
                    self._send_json(200, {"message": f"Opened in VS Code: {target}"})
                elif act == "run":
                    target = Path(payload.get("path"))
                    if target.suffix == ".py":
                        subprocess.Popen(f'start cmd /k python "{target}"', shell=True)
                    else:
                        subprocess.Popen(f'start "" "{target}"', shell=True)
                    self._send_json(200, {"message": f"Started {target.name}"})
                else:
                    self._send_json(400, {"error": "Invalid action."})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        elif u.path == "/api/terminal":
            cmd = payload.get("command", "")
            cwd = payload.get("cwd", None)
            try:
                res = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=cwd if cwd and os.path.exists(cwd) else None,
                    timeout=15
                )
                output = res.stdout if res.stdout else res.stderr
                self._send_json(200, {"output": output or "Process completed with no output."})
            except subprocess.TimeoutExpired:
                self._send_json(200, {"output": "Error: Command timed out after 15 seconds."})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "Endpoint not found"})

    def log_message(self, *args):
        pass

if __name__ == "__main__":
    ip = get_local_ip()
    print("=" * 60)
    print("KIA ULTIMATE PC REMOTE SERVER")
    print("=" * 60)
    print(f"Server IP : {ip}")
    print(f"Port      : {PORT}")
    print(f"Open URL  : http://{ip}:{PORT}/?token={TOKEN}")
    print("=" * 60)
    print("Keep this script running. Open the URL in your phone's browser.")
    ThreadingHTTPServer((HOST, PORT), KIAHandler).serve_forever()
