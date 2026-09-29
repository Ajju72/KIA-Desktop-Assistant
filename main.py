import sys
import os
import time
import re
import asyncio
import tempfile
import subprocess
import webbrowser
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime

# ------------------------------------------------------------
# KIA - Standalone JARVIS-style AI Desktop Assistant
# Designed to run from VS Code with Python 3.13 / 3.14
# ------------------------------------------------------------

# Load environment variables from the project, independent of launch folder.
try:
    from dotenv import load_dotenv
    BASE_DIR = Path(__file__).resolve().parent
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        env_file = BASE_DIR / "project.env"
    load_dotenv(env_file, override=False)
except Exception:
    pass


try:
    from PySide6.QtCore import Qt, QTimer, QThread, Signal, QPointF
    from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QRadialGradient
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QTextEdit, QLineEdit, QPushButton, QLabel, QFrame, QMessageBox,
        QProgressBar, QGridLayout
    )
except ImportError as e:
    print("\nERROR: PySide6 could not be imported.")
    print("Python:", sys.executable)
    print("Error:", e)
    print("\nRun:")
    print(f'"{sys.executable}" -m pip install PySide6')
    input("\nPress Enter to exit...")
    sys.exit(1)

# Optional modules
try:
    import psutil
except Exception:
    psutil = None

try:
    import pyperclip
except Exception:
    pyperclip = None

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import edge_tts
except Exception:
    edge_tts = None

try:
    import pygame
except Exception:
    pygame = None

try:
    import certifi
except Exception:
    certifi = None

# Audio input libraries (sounddevice bypasses pyaudio build errors on Python 3.14)
try:
    import speech_recognition as sr
except Exception:
    sr = None

try:
    import sounddevice as sd
    import numpy as np
except Exception:
    sd = None
    np = None


APP_NAME = "KIA"
MODEL = (
    os.getenv("GROQ_MODEL")
    or os.getenv("AI_MODEL")
    or "openai/gpt-oss-120b"
).strip()
API_KEY = (
    os.getenv("GROQ_API_KEY")
    or os.getenv("AI_API_KEY")
    or ""
).strip()
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
HTTPS_CONTEXT = (
    ssl.create_default_context(cafile=certifi.where())
    if certifi is not None
    else ssl.create_default_context()
)

VOICE_EN = os.getenv("KIA_VOICE_EN", "en-IN-NeerjaNeural")
VOICE_HI = os.getenv("KIA_VOICE_HI", "hi-IN-SwaraNeural")

MEMORY_FILE = Path.home() / "kia_memory.txt"


def open_url(url):
    webbrowser.open(url)


def open_app(name):
    aliases = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "edge": "msedge",
        "microsoft edge": "msedge",
        "notepad": "notepad",
        "calculator": "calc",
        "calc": "calc",
        "paint": "mspaint",
        "explorer": "explorer",
        "file explorer": "explorer",
        "cmd": "cmd",
        "terminal": "wt",
        "powershell": "powershell",
        "task manager": "taskmgr",
        "settings": "start ms-settings:",
        "control panel": "control",
        "camera": "start microsoft.windows.camera:",
        "vscode": "code",
        "code": "code",
        "spotify": "spotify",
        "vlc": "vlc",
    }
    cmd = aliases.get(name.lower().strip(), name.lower().strip())
    try:
        subprocess.Popen(cmd, shell=True)
        return True
    except Exception:
        return False


def close_app(name):
    aliases = {
        "chrome": "chrome.exe",
        "google chrome": "chrome.exe",
        "edge": "msedge.exe",
        "notepad": "notepad.exe",
        "calculator": "CalculatorApp.exe",
        "calc": "CalculatorApp.exe",
        "paint": "mspaint.exe",
        "cmd": "cmd.exe",
        "code": "Code.exe",
        "vscode": "Code.exe",
        "spotify": "Spotify.exe",
        "vlc": "vlc.exe",
        "task manager": "Taskmgr.exe",
    }
    target = aliases.get(name.lower().strip(), f"{name.strip()}.exe")
    try:
        subprocess.Popen(f"taskkill /f /im {target}", shell=True)
        return True
    except Exception:
        return False


class VoiceListenerWorker(QThread):
    """Background voice listener thread that captures audio and translates speech to text."""
    voice_command_signal = Signal(str)
    status_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.is_running = True

    def run(self):
        if sr is None:
            self.status_signal.emit("speech_recognition library not installed.")
            return

        recognizer = sr.Recognizer()

        # sounddevice avoids the PyAudio build requirement on Python 3.14.
        if sd is not None and np is not None:
            sample_rate = 16000
            duration = 3.5

            while self.is_running:
                try:
                    self.status_signal.emit("LISTENING")
                    recording = sd.rec(
                        int(duration * sample_rate),
                        samplerate=sample_rate,
                        channels=1,
                        dtype="int16"
                    )
                    sd.wait()

                    if not self.is_running:
                        break

                    # Audio energy threshold filter (ignores room silence)
                    volume_norm = np.linalg.norm(recording)
                    if volume_norm < 650:
                        continue

                    self.status_signal.emit("PROCESSING VOICE")
                    raw_bytes = recording.tobytes()
                    audio_data = sr.AudioData(raw_bytes, sample_rate, 2)
                    text = recognizer.recognize_google(audio_data, language="en-IN")
                    if text.strip() and self.is_running:
                        self.voice_command_signal.emit(text.strip())

                except sr.UnknownValueError:
                    continue
                except Exception as e:
                    self.status_signal.emit(f"MIC ERROR: {e}")
                    self.msleep(500)
        else:
            self.status_signal.emit(
                "Voice input unavailable. Install sounddevice and numpy."
            )

    def stop(self):
        self.is_running = False
        if sd is not None:
            try:
                sd.stop()
            except Exception:
                pass
        self.quit()
        self.wait()


class VoiceWorker(QThread):
    finished_signal = Signal(str)

    def __init__(self, text):
        super().__init__()
        self.text = text

    def run(self):
        if edge_tts is None or pygame is None:
            self.finished_signal.emit("fallback")
            return

        try:
            voice = VOICE_HI if any(
                "\u0900" <= ch <= "\u097F" for ch in self.text
            ) else VOICE_EN

            async def create_audio():
                communicate = edge_tts.Communicate(
                    self.text, voice=voice, rate="+0%", volume="+0%"
                )
                fd, filename = tempfile.mkstemp(suffix=".mp3")
                os.close(fd)
                await communicate.save(filename)
                return filename

            filename = asyncio.run(create_audio())

            pygame.mixer.init()
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(20)

            pygame.mixer.quit()
            try:
                os.remove(filename)
            except Exception:
                pass

            self.finished_signal.emit("ok")
        except Exception:
            self.finished_signal.emit("fallback")


class AIWorker(QThread):
    answer_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, prompt):
        super().__init__()
        self.prompt = prompt

    def run(self):
        if not API_KEY:
            self.error_signal.emit(
                "Groq API key not found. Add GROQ_API_KEY=YOUR_KEY to project.env."
            )
            return
        system = """
You are KIA, a futuristic desktop AI assistant inspired by JARVIS.
Be intelligent, calm, concise and helpful.
The user can speak Hindi, English or Hinglish.
Reply in the same language as the user when possible.
Do not claim to control something unless the desktop application actually performed that action.
For normal questions, give useful answers without unnecessary filler.
"""

        try:
            payload = json.dumps({
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system.strip()},
                    {"role": "user", "content": self.prompt},
                ],
                "stream": False,
            }).encode("utf-8")
            request = urllib.request.Request(
                GROQ_API_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": "KIA-Desktop-Assistant/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(
                request,
                timeout=45,
                context=HTTPS_CONTEXT,
            ) as response:
                result = json.loads(response.read().decode("utf-8"))
            text = result["choices"][0]["message"]["content"]
            self.answer_signal.emit(text.strip())
        except urllib.error.HTTPError as e:
            try:
                details = json.loads(e.read().decode("utf-8"))
                message = details.get("error", {}).get("message", str(e))
            except Exception:
                message = str(e)
            if e.code == 401:
                self.error_signal.emit(
                    "Groq API key is invalid. Create a new key at console.groq.com "
                    "and update GROQ_API_KEY in project.env."
                )
            elif e.code == 429:
                self.error_signal.emit(
                    f"Groq rate limit or quota reached: {message}"
                )
            elif e.code == 402:
                self.error_signal.emit(
                    "Groq accepted the API key, but the account has no available quota. "
                    "Check usage and limits at console.groq.com, then try again."
                )
            elif e.code == 403:
                self.error_signal.emit(
                    "Groq denied this request (403). Check that the API key is active, "
                    "authorized for the Groq API, and not restricted by the network."
                )
            elif e.code == 404:
                self.error_signal.emit(
                    f"Groq model '{MODEL}' is unavailable. Set GROQ_MODEL to a supported "
                    "model from the Groq models list in project.env."
                )
            else:
                self.error_signal.emit(f"Groq API error ({e.code}): {message}")
        except (urllib.error.URLError, TimeoutError) as e:
            self.error_signal.emit(f"Could not reach Groq: {e}")
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            self.error_signal.emit(f"Unexpected Groq response: {e}")
        except Exception as e:
            error_text = str(e)
            error_lower = error_text.lower()
            if (
                "429" in error_lower
                or "quota" in error_lower
                or "resource_exhausted" in error_lower
            ):
                retry_match = re.search(r"retryDelay.*?(\d+)s", error_text)
                retry_hint = (
                    f" Retry after about {retry_match.group(1)} seconds if this is a "
                    "short rate limit."
                    if retry_match
                    else ""
                )
                self.error_signal.emit(
                    "Groq quota is exhausted for this project/model."
                    f"{retry_hint} Daily free-tier limits require waiting for reset "
                    "or using another API project with billing enabled."
                )
            else:
                self.error_signal.emit(f"Groq error: {error_text}")


class ArcReactor(QWidget):
    def __init__(self):
        super().__init__()
        self.phase = 0
        self.setMinimumSize(300, 300)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(30)

    def animate(self):
        self.phase = (self.phase + 3) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cx = self.width() / 2
        cy = self.height() / 2
        center = QPointF(cx, cy)

        # Outer rings
        for radius, alpha, width in [
            (125, 35, 2),
            (105, 60, 2),
            (85, 90, 3),
            (60, 130, 3),
        ]:
            pen = QPen(QColor(0, 220, 255, alpha), width)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, radius, radius)

        # Glow
        gradient = QRadialGradient(center, 55)
        gradient.setColorAt(0.0, QColor(210, 255, 255, 230))
        gradient.setColorAt(0.25, QColor(0, 235, 255, 180))
        gradient.setColorAt(0.65, QColor(0, 120, 220, 60))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(center, 58, 58)

        # Core
        painter.setBrush(QBrush(QColor(180, 250, 255)))
        painter.drawEllipse(center, 24, 24)

        # Rotating markers
        import math
        for i in range(8):
            angle = math.radians(self.phase + i * 45)
            x = cx + math.cos(angle) * 112
            y = cy + math.sin(angle) * 112
            painter.setBrush(QBrush(QColor(0, 240, 255)))
            painter.drawEllipse(QPointF(x, y), 4, 4)

        painter.setPen(QPen(QColor(120, 240, 255), 1))
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.drawText(
            self.rect().adjusted(0, 135, 0, 0),
            Qt.AlignHCenter,
            "KIA CORE ONLINE"
        )


class KIAWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.ai_worker = None
        self.voice_worker = None
        self.listener_worker = None

        self.setWindowTitle("KIA — AI Desktop Assistant")
        self.resize(1200, 760)
        self.setMinimumSize(950, 650)

        self.build_ui()
        self.apply_style()
        self.update_system_info()

        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self.update_system_info)
        self.stats_timer.start(1500)

        self.log("KIA system initialized.")
        self.log(f"Python: {sys.version.split()[0]}")
        self.log(f"Interpreter: {sys.executable}")
        self.log(f"Groq: {'CONFIGURED' if API_KEY else 'NOT CONFIGURED'}")
        self.log(f"Model: {MODEL}")

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        main = QHBoxLayout(root)
        main.setContentsMargins(18, 18, 18, 18)
        main.setSpacing(18)

        # Left HUD
        left = QFrame()
        left.setObjectName("panel")
        left_layout = QVBoxLayout(left)
        left_layout.setAlignment(Qt.AlignTop)

        title = QLabel("K I A")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("AI DESKTOP ASSISTANT")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)

        self.core = ArcReactor()

        self.status = QLabel("● SYSTEM ONLINE")
        self.status.setObjectName("online")
        self.status.setAlignment(Qt.AlignCenter)

        left_layout.addWidget(title)
        left_layout.addWidget(subtitle)
        left_layout.addWidget(self.core, 1)
        left_layout.addWidget(self.status)

        # Right console
        right = QFrame()
        right.setObjectName("panel")
        right_layout = QVBoxLayout(right)

        header = QHBoxLayout()
        self.time_label = QLabel("--:--:--")
        self.time_label.setObjectName("clock")

        self.model_label = QLabel(f"GROQ / {MODEL}")
        self.model_label.setObjectName("model")

        header.addWidget(self.model_label)
        header.addStretch()
        header.addWidget(self.time_label)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("KIA conversation console...")

        self.input = QLineEdit()
        self.input.setPlaceholderText(
            "Type or speak... e.g. 'open notepad', 'volume up', 'shutdown pc', 'screenshot'"
        )
        self.input.returnPressed.connect(self.send_message)

        send = QPushButton("SEND  ▶")
        send.clicked.connect(self.send_message)

        controls = QHBoxLayout()

        self.mic_btn = QPushButton("🎤 MIC: OFF")
        self.mic_btn.clicked.connect(self.toggle_voice_listener)
        controls.addWidget(self.mic_btn)

        for text, fn in [
            ("WEB", lambda: self.quick("search")),
            ("YOUTUBE", lambda: self.quick("youtube")),
            ("SCREENSHOT", self.screenshot),
            ("SYSTEM SCAN", self.system_scan),
            ("CLEAR", self.chat.clear),
        ]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            controls.addWidget(b)

        stats = QGridLayout()
        self.cpu = self.stat_box("CPU")
        self.ram = self.stat_box("RAM")
        self.bat = self.stat_box("BATTERY")
        self.disk = self.stat_box("DISK")
        self.net = self.stat_box("NETWORK")
        self.python = self.stat_box("PYTHON")

        boxes = [self.cpu, self.ram, self.bat, self.disk, self.net, self.python]
        for i, box in enumerate(boxes):
            stats.addWidget(box, i // 3, i % 3)

        entry = QHBoxLayout()
        entry.addWidget(self.input, 1)
        entry.addWidget(send)

        right_layout.addLayout(header)
        right_layout.addLayout(stats)
        right_layout.addWidget(self.chat, 1)
        right_layout.addLayout(controls)
        right_layout.addLayout(entry)

        main.addWidget(left, 1)
        main.addWidget(right, 2)

    def stat_box(self, name):
        label = QLabel(f"{name}\n--")
        label.setAlignment(Qt.AlignCenter)
        label.setObjectName("stat")
        return label

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #050a12;
                color: #d8faff;
                font-family: "Segoe UI";
            }

            QFrame#panel {
                background: #08121d;
                border: 1px solid #123b4a;
                border-radius: 18px;
            }

            QLabel#title {
                color: #7ff6ff;
                font-size: 38px;
                font-weight: 800;
                letter-spacing: 8px;
            }

            QLabel#subtitle {
                color: #5593a2;
                font-size: 11px;
                letter-spacing: 3px;
            }

            QLabel#online {
                color: #5fffc4;
                font-weight: 700;
                padding: 10px;
            }

            QLabel#clock {
                color: #83efff;
                font-size: 20px;
                font-weight: 700;
            }

            QLabel#model {
                color: #508b9b;
                font-size: 11px;
            }

            QLabel#stat {
                background: #06101a;
                border: 1px solid #164354;
                border-radius: 10px;
                padding: 8px;
                color: #70e8f5;
                font-weight: 700;
            }

            QTextEdit, QLineEdit {
                background: #03080e;
                border: 1px solid #17485a;
                border-radius: 12px;
                padding: 12px;
                color: #d8faff;
                selection-background-color: #07566b;
            }

            QPushButton {
                background: #09202b;
                border: 1px solid #176277;
                border-radius: 9px;
                padding: 9px 13px;
                color: #78eefa;
                font-weight: 700;
            }

            QPushButton:hover {
                background: #0d3443;
                border: 1px solid #3cecff;
            }

            QPushButton:pressed {
                background: #0a5669;
            }
        """)

    def log(self, text, speaker="KIA"):
        now = datetime.now().strftime("%H:%M:%S")
        self.chat.append(
            f'<span style="color:#4f8190">[{now}]</span> '
            f'<span style="color:#65efff"><b>{speaker}:</b></span> '
            f'{text.replace(chr(10), "<br>")}'
        )

    def toggle_voice_listener(self):
        if self.listener_worker and self.listener_worker.isRunning():
            self.listener_worker.stop()
            self.listener_worker = None
            self.mic_btn.setText("🎤 MIC: OFF")
            self.mic_btn.setStyleSheet("")
            self.status.setText("● SYSTEM ONLINE")
            self.status.setStyleSheet("color:#5fffc4; font-weight:700;")
            self.log("Voice listener disabled.")
        else:
            if sr is None:
                self.log("Install speech_recognition and sounddevice: pip install SpeechRecognition sounddevice numpy", "ERROR")
                return
            self.mic_btn.setText("🔴 MIC: ON")
            self.mic_btn.setStyleSheet("background: #541414; border: 1px solid #ff4d4d; color: #ffbfbf;")
            self.log("Voice listener activated. Speak clearly.")
            self.listener_worker = VoiceListenerWorker()
            self.listener_worker.voice_command_signal.connect(self.handle_voice_input)
            self.listener_worker.status_signal.connect(self.handle_listener_status)
            self.listener_worker.start()

    def handle_listener_status(self, status):
        if "LISTENING" in status:
            self.status.setText("● LISTENING...")
            self.status.setStyleSheet("color:#00e5ff; font-weight:700;")
        elif "PROCESSING" in status:
            self.status.setText("● PROCESSING VOICE")
            self.status.setStyleSheet("color:#ffd166; font-weight:700;")
        else:
            self.status.setText(f"● {status}")

    def handle_voice_input(self, text):
        cleaned = text.strip()
        if not cleaned:
            return

        # Wake-word filter to protect API free-tier quotas from background noise
        if "kia" in cleaned.lower():
            cleaned = cleaned.lower().replace("kia", "").strip()
            if not cleaned:
                self.log("Yes, I am online and listening.", "KIA")
                self.speak("Yes, I am listening.")
                return

        self.process_query(cleaned, speaker="YOU (VOICE)")

    def send_message(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.process_query(text, speaker="YOU")

    def process_query(self, text, speaker="YOU"):
        self.log(text, speaker)
        self.status.setText("● EXECUTING")
        self.status.setStyleSheet("color:#ffd166; font-weight:700;")

        # Local PC controls executed first without making external AI calls
        if self.handle_command(text):
            self.status.setText("● SYSTEM ONLINE")
            self.status.setStyleSheet("color:#5fffc4; font-weight:700;")
            return

        # AI conversational fallback
        self.ai_worker = AIWorker(text)
        self.ai_worker.answer_signal.connect(self.ai_answer)
        self.ai_worker.error_signal.connect(self.ai_error)
        self.ai_worker.finished.connect(self.ai_finished)
        self.ai_worker.start()

    def ai_answer(self, text):
        self.log(text)
        self.speak(text)

    def ai_error(self, text):
        self.log(text, "ERROR")

    def ai_finished(self):
        self.status.setText("● SYSTEM ONLINE")
        self.status.setStyleSheet("color:#5fffc4; font-weight:700;")

    def speak(self, text):
        spoken = text.replace("*", "").replace("#", "")
        if len(spoken) > 700:
            spoken = spoken[:700] + "..."

        if edge_tts is None or pygame is None:
            return

        if self.voice_worker and self.voice_worker.isRunning():
            return

        self.voice_worker = VoiceWorker(spoken)
        self.voice_worker.start()

    def handle_command(self, text):
        q = text.lower().strip()

        # Greetings
        if q in ("hello", "hi kia", "hey kia", "hello kia"):
            msg = "Hello. KIA is online and ready. How can I assist you?"
            self.log(msg)
            self.speak(msg)
            return True

        # Volume Controls
        if "volume up" in q or "increase volume" in q or "awaz badhao" in q:
            if pyautogui:
                pyautogui.press("volumeup", presses=5)
            self.log("Volume increased.")
            return True

        if "volume down" in q or "decrease volume" in q or "awaz kam karo" in q:
            if pyautogui:
                pyautogui.press("volumedown", presses=5)
            self.log("Volume decreased.")
            return True

        if q in ("mute", "unmute", "mute audio", "mute sound"):
            if pyautogui:
                pyautogui.press("volumemute")
            self.log("Audio mute toggled.")
            return True

        # Media Controls
        if q in ("play", "pause", "play audio", "pause video", "play video", "resume"):
            if pyautogui:
                pyautogui.press("playpause")
            self.log("Media playback toggled.")
            return True

        if "next song" in q or "next track" in q:
            if pyautogui:
                pyautogui.press("nexttrack")
            self.log("Skipping to next track.")
            return True

        if "previous song" in q or "previous track" in q:
            if pyautogui:
                pyautogui.press("prevtrack")
            self.log("Playing previous track.")
            return True

        # Window & Desktop Control
        if q in ("minimize", "minimize all", "show desktop"):
            if pyautogui:
                pyautogui.hotkey("win", "d")
            self.log("Desktop toggled.")
            return True

        if q in ("switch window", "next window", "alt tab"):
            if pyautogui:
                pyautogui.hotkey("alt", "tab")
            self.log("Switched active window.")
            return True

        if q in ("close window", "close current window", "band karo"):
            if pyautogui:
                pyautogui.hotkey("alt", "f4")
            self.log("Closing active window.")
            return True

        # Mouse & Keystroke Automation
        if "scroll down" in q:
            if pyautogui:
                pyautogui.scroll(-500)
            self.log("Scrolling down.")
            return True

        if "scroll up" in q:
            if pyautogui:
                pyautogui.scroll(500)
            self.log("Scrolling up.")
            return True

        if q.startswith("type "):
            content = text[5:].strip()
            if pyautogui:
                pyautogui.write(content, interval=0.03)
            self.log(f"Typed: {content}")
            return True

        if q in ("press enter", "hit enter"):
            if pyautogui:
                pyautogui.press("enter")
            self.log("Pressed Enter.")
            return True

        # Open Applications
        if q.startswith("open "):
            target = q[5:].strip()
            if open_app(target):
                msg = f"Opening {target}."
            else:
                msg = f"I couldn't find a local app named {target}."
            self.log(msg)
            self.speak(msg)
            return True

        # Close Applications
        if q.startswith("close ") or q.startswith("kill "):
            target = q.replace("close ", "").replace("kill ", "").strip()
            if close_app(target):
                msg = f"Closing {target}."
            else:
                msg = f"Could not close {target}."
            self.log(msg)
            self.speak(msg)
            return True

        # Quick Web Services
        if "youtube" in q and ("open" in q or "play" in q):
            open_url("https://www.youtube.com")
            self.log("Opening YouTube.")
            self.speak("Opening YouTube.")
            return True

        if q.startswith("search ") or q.startswith("web search "):
            query = q.replace("web search ", "", 1).replace("search ", "", 1)
            open_url("https://www.google.com/search?q=" + query.replace(" ", "+"))
            self.log(f"Searching the web for: {query}")
            self.speak("Searching the web.")
            return True

        if "google maps" in q or q.startswith("maps "):
            query = q.replace("google maps", "").replace("maps", "").strip()
            open_url("https://www.google.com/maps/search/" + query.replace(" ", "+"))
            self.log("Opening Google Maps.")
            return True

        if "wikipedia" in q:
            query = q.replace("wikipedia", "").strip()
            open_url("https://en.wikipedia.org/wiki/" + query.replace(" ", "_"))
            self.log("Opening Wikipedia.")
            return True

        if q in ("screenshot", "take screenshot", "take a screenshot"):
            self.screenshot()
            return True

        if q in ("system scan", "system status", "system info"):
            self.system_scan()
            return True

        if q in ("copy", "copy clipboard"):
            if pyperclip:
                self.log("Clipboard support is ready.")
            return True

        # Memory Functions
        if q.startswith("remember "):
            note = text[9:].strip()
            try:
                with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                    f.write(note + "\n")
                self.log("Memory saved.")
                self.speak("Memory saved.")
            except Exception as e:
                self.log(f"Memory error: {e}", "ERROR")
            return True

        if q in ("show memory", "my memory", "memory"):
            try:
                if MEMORY_FILE.exists():
                    content = MEMORY_FILE.read_text(encoding="utf-8").strip()
                    self.log(content if content else "Memory is empty.")
                else:
                    self.log("Memory is empty.")
            except Exception as e:
                self.log(str(e), "ERROR")
            return True

        # PC Power Management
        if q in ("lock pc", "lock computer", "lock"):
            try:
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
                self.log("System locked.")
                return True
            except Exception as e:
                self.log(str(e), "ERROR")
                return True

        if "shutdown pc" in q or "turn off pc" in q:
            msg = "Initiating system shutdown in 30 seconds. Say 'cancel shutdown' to abort."
            self.log(msg)
            self.speak(msg)
            subprocess.Popen("shutdown /s /t 30", shell=True)
            return True

        if "restart pc" in q or "reboot pc" in q:
            msg = "Restarting PC in 30 seconds."
            self.log(msg)
            self.speak(msg)
            subprocess.Popen("shutdown /r /t 30", shell=True)
            return True

        if "cancel shutdown" in q or "abort shutdown" in q:
            subprocess.Popen("shutdown /a", shell=True)
            self.log("Shutdown aborted successfully.")
            self.speak("Shutdown cancelled.")
            return True

        if "sleep pc" in q or "put pc to sleep" in q:
            self.log("Putting system to sleep.")
            subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
            return True

        if "empty recycle bin" in q or "clear trash" in q:
            subprocess.Popen("powershell.exe -Command Clear-RecycleBin -Force -ErrorAction SilentlyContinue", shell=True)
            self.log("Recycle bin cleared.")
            return True

        return False

    def quick(self, kind):
        if kind == "search":
            self.input.setText("search ")
            self.input.setFocus()
        elif kind == "youtube":
            open_url("https://www.youtube.com")
            self.log("Opening YouTube.")
        else:
            pass

    def screenshot(self):
        folder = Path.home() / "Pictures" / "KIA Screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        filename = folder / f"KIA_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        try:
            if pyautogui:
                image = pyautogui.screenshot()
                image.save(filename)
                self.log(f"Screenshot saved: {filename}")
                self.speak("Screenshot saved.")
            else:
                self.log(
                    "PyAutoGUI is not available. Install it with "
                    f'"{sys.executable}" -m pip install pyautogui',
                    "ERROR"
                )
        except Exception as e:
            self.log(f"Screenshot error: {e}", "ERROR")

    def system_scan(self):
        if psutil is None:
            self.log("psutil is not installed.", "ERROR")
            return

        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent

        battery = psutil.sensors_battery()
        bat = f"{battery.percent:.0f}%" if battery else "N/A"

        self.log(
            f"System scan — CPU {cpu:.0f}% | RAM {ram:.0f}% | "
            f"Disk {disk:.0f}% | Battery {bat}"
        )

    def update_system_info(self):
        self.time_label.setText(datetime.now().strftime("%H:%M:%S"))

        if psutil:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage("/").percent

            battery = psutil.sensors_battery()
            bat = f"{battery.percent:.0f}%" if battery else "N/A"

            self.cpu.setText(f"CPU\n{cpu:.0f}%")
            self.ram.setText(f"RAM\n{ram:.0f}%")
            self.disk.setText(f"DISK\n{disk:.0f}%")
            self.bat.setText(f"BATTERY\n{bat}")

            try:
                net = psutil.net_io_counters()
                self.net.setText(
                    f"NETWORK\n↓ {net.bytes_recv // 1024 // 1024} MB"
                )
            except Exception:
                self.net.setText("NETWORK\nOK")
        else:
            self.cpu.setText("CPU\nN/A")
            self.ram.setText("RAM\nN/A")
            self.disk.setText("DISK\nN/A")
            self.bat.setText("BATTERY\nN/A")
            self.net.setText("NETWORK\nN/A")

        self.python.setText(f"PYTHON\n{sys.version_info.major}.{sys.version_info.minor}")

    def closeEvent(self, event):
        if self.listener_worker and self.listener_worker.isRunning():
            self.listener_worker.stop()
        event.accept()


def main():
    print("=" * 55)
    print("              KIA — AI DESKTOP ASSISTANT")
    print("=" * 55)
    print("Python:", sys.version.split()[0])
    print("Interpreter:", sys.executable)
    print("Groq API:", "Configured" if API_KEY else "NOT CONFIGURED")
    print("Groq Model:", MODEL)
    print("=" * 55)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    window = KIAWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
