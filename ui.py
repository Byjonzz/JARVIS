"""ui.py — I.R.I.S. HUD v2 (pantalla completa, widgets funcionales, voz animada)

La página assets/hud.html dibuja todo; este archivo es el puente:
- señales de main.py → JavaScript (estado, log, transcripciones, nivel de voz)
- widgets → Python (volumen del sistema, tema, ajustes, minimizar, cerrar)
- estadísticas en vivo (CPU/RAM cada 2s; cerebro/guardián/volumen cada 10s)
"""
from __future__ import annotations
import sys
import os
import json
import threading
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, pyqtSlot, QObject, QTimer
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

from settings_window import DeviceSettingsDialog

try:
    from config_manager import load_api_keys, save_api_keys
except ImportError:
    def load_api_keys(): return {}
    def save_api_keys(cfg): pass

_BA_TZ = timezone(timedelta(hours=-6))

THEMES = {
    "green": {"PRI": "#00FF00", "PRI_DIM": "#00CC00", "BG": "#000000", "TEXT": "#FFFFFF", "BORDER": "rgba(0, 255, 0, 0.45)"},
    "cyan": {"PRI": "#00FFFF", "PRI_DIM": "#00CCCC", "BG": "#000000", "TEXT": "#FFFFFF", "BORDER": "rgba(0, 255, 255, 0.45)"},
    "red": {"PRI": "#FF0000", "PRI_DIM": "#CC0000", "BG": "#000000", "TEXT": "#FFFFFF", "BORDER": "rgba(255, 0, 0, 0.45)"},
    "purple": {"PRI": "#9D00FF", "PRI_DIM": "#7A00CC", "BG": "#000000", "TEXT": "#FFFFFF", "BORDER": "rgba(157, 0, 255, 0.45)"},
    "gold": {"PRI": "#f59e0b", "PRI_DIM": "#d97706", "BG": "#0c0804", "TEXT": "#fde68a", "BORDER": "rgba(245, 158, 11, 0.45)"},
    "white": {"PRI": "#FFFFFF", "PRI_DIM": "#CCCCCC", "BG": "#000000", "TEXT": "#FFFFFF", "BORDER": "rgba(255, 255, 255, 0.45)"}
}

C_PRI = THEMES["white"]["PRI"]
C_PRI_DIM = THEMES["white"]["PRI_DIM"]
C_TEXT = THEMES["white"]["TEXT"]
C_BORDER = THEMES["white"]["BORDER"]

def set_global_theme(theme_name):
    global C_PRI, C_PRI_DIM, C_TEXT, C_BORDER
    t = THEMES.get(theme_name, THEMES["green"])
    C_PRI = t["PRI"]
    C_PRI_DIM = t["PRI_DIM"]
    C_TEXT = t["TEXT"]
    C_BORDER = t["BORDER"]

class WebBridge(QObject):
    """Lo que los widgets del HUD pueden pedirle a Python."""

    def __init__(self, orb):
        super().__init__()
        self.orb = orb

    @pyqtSlot()
    def request_theme(self):
        QTimer.singleShot(0, self.orb.sync_theme)

    @pyqtSlot()
    def close_app(self):
        QApplication.quit()

    @pyqtSlot()
    def minimize_app(self):
        if self.orb.ui and hasattr(self.orb.ui, '_win'):
            self.orb.ui._win.showMinimized()

    @pyqtSlot()
    def open_settings(self):
        if self.orb.ui and hasattr(self.orb.ui, '_win'):
            self.orb.ui._win._open_settings()

    @pyqtSlot(int)
    def set_system_volume(self, nivel):
        """Widget de volumen → volumen maestro real de Windows (en un hilo:
        la llamada COM no debe congelar la interfaz)."""
        def aplicar():
            try:
                from actions import volume_control
                volume_control.volume_control({"action": "set", "level": int(nivel)})
            except Exception:
                pass
        threading.Thread(target=aplicar, daemon=True).start()

    @pyqtSlot(str)
    def set_theme(self, nombre):
        """Widget de temas → aplica y PERSISTE el tema elegido."""
        if nombre not in THEMES:
            return
        try:
            cfg = load_api_keys()
            cfg["jarvis_theme"] = nombre
            save_api_keys(cfg)
        except Exception:
            pass
        if self.orb.ui and hasattr(self.orb.ui, '_win'):
            self.orb.ui._win.apply_new_theme(nombre)

    @pyqtSlot(int, int)
    def move_window(self, dx, dy):
        pass  # pantalla completa absoluta

class CustomParticleOrb(QWidget):
    audio_signal = pyqtSignal(float)   # nivel del micrófono (usuario)
    voice_signal = pyqtSignal(float)   # nivel de la VOZ de I.R.I.S. (animación al hablar)
    state_signal = pyqtSignal(str)
    theme_signal = pyqtSignal()

    def __init__(self, ui, parent=None):
        super().__init__(parent)
        self.ui = ui
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--enable-webgl --ignore-gpu-blocklist --enable-gpu-rasterization"

        self.web_view = QWebEngineView(self)
        self.web_view.setStyleSheet("background: #000000;")

        try:
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            settings = self.web_view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        except Exception:
            pass

        self.channel = QWebChannel()
        self.bridge = WebBridge(self)
        self.channel.registerObject("pyBridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        hud_path = Path(__file__).parent / "assets" / "hud.html"
        self.web_view.setUrl(QUrl.fromLocalFile(str(hud_path.absolute())))
        layout.addWidget(self.web_view)

        self.audio_signal.connect(self._safe_set_audio)
        self.voice_signal.connect(self._safe_set_voice)
        self.state_signal.connect(self._safe_set_state)
        self.theme_signal.connect(self._safe_sync_theme)
        self.web_view.loadFinished.connect(self._on_load_finished)

    def _on_load_finished(self, ok):
        if ok:
            self.sync_theme()
            self.set_state("IDLE")

    def _js(self, codigo):
        try:
            self.web_view.page().runJavaScript(codigo)
        except Exception:
            pass

    def sync_theme(self): self.theme_signal.emit()
    def set_audio(self, level: float): self.audio_signal.emit(level)
    def set_voice(self, level: float): self.voice_signal.emit(level)
    def set_state(self, state: str): self.state_signal.emit(state)

    def _safe_sync_theme(self):
        colors = {'PRI': C_PRI, 'PRI_DIM': C_PRI_DIM, 'TEXT': C_TEXT, 'BORDER': C_BORDER}
        self._js(f"if (window.setThemeColors) window.setThemeColors({json.dumps(colors)});")

    def _safe_set_audio(self, level: float):
        self._js(f"if (window.updateVolume) window.updateVolume({level});")

    def _safe_set_voice(self, level: float):
        self._js(f"if (window.updateVoice) window.updateVoice({level});")

    def _safe_set_state(self, state: str):
        self._js(f"if (window.updateState) window.updateState('{state}');")

class MainWindow(QMainWindow):
    def __init__(self, ui, face_path):
        super().__init__()
        self.ui = ui
        self.ui._win = self

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: black;")

        self.orb = CustomParticleOrb(self.ui, self)
        self.setCentralWidget(self.orb)

        # 📊 Estadísticas lentas (cerebro, guardián, volumen real, catálogo) en un
        # hilo demonio: leer archivos o COM jamás congela la interfaz.
        self._stats_lentas = {}
        threading.Thread(target=self._ciclo_stats_lentas, daemon=True).start()

        self._tick_n = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()

    def tick(self):
        try:
            now = datetime.now(_BA_TZ)
            time_str = now.strftime("%I:%M:%S %p")
            date_str = now.strftime("%A, %d %B %Y").upper()
            self.orb._js(f"if (window.updateClock) window.updateClock('{time_str}', '{date_str}');")

            self._tick_n += 1
            if self._tick_n % 2 == 0:
                stats = dict(self._stats_lentas)
                try:
                    import psutil
                    vm = psutil.virtual_memory()
                    stats["cpu"] = psutil.cpu_percent(None)
                    stats["ram"] = vm.percent
                    stats["ram_gb"] = f"{vm.used / 2**30:.1f} GB"
                except Exception:
                    pass
                self.orb._js(f"if (window.updateStats) window.updateStats({json.dumps(stats)});")
        except Exception:
            pass

    def _ciclo_stats_lentas(self):
        base = Path(__file__).parent
        while True:
            datos = {}
            try:
                cfg = load_api_keys()
                datos["mic"] = (cfg.get("mic_device_name") or "auto")[:26]
                datos["spk"] = (cfg.get("speaker_device_name") or "auto")[:26]
                datos["calidad"] = cfg.get("performance_quality", 87)

                # 🧠 Cerebro: catálogo y aprendizaje
                try:
                    datos["tools"] = len([a for a in os.listdir(base / "actions")
                                          if a.endswith(".py") and a != "__init__.py"])
                except Exception:
                    pass
                meta = base / "config" / "neural_meta.json"
                if meta.exists():
                    m = json.loads(meta.read_text(encoding="utf-8"))
                    datos["precision"] = int(round(float(m.get("precision", 0)) * 100))
                dataset = base / "config" / "neural_dataset.jsonl"
                if dataset.exists():
                    with open(dataset, encoding="utf-8") as f:
                        datos["ejemplos"] = sum(1 for linea in f if linea.strip())

                # 🗝️ Guardián de voz
                lock = bool(cfg.get("voice_lock", True))
                huella = (base / "config" / "voice_profile.npz").exists()
                datos["guard_estado"] = "ACTIVO" if (lock and huella) else ("SIN HUELLA" if lock else "APAGADO")
                datos["guard_huella"] = "GRABADA" if huella else "PENDIENTE"
                datos["guard_rig"] = f"{cfg.get('voice_strictness', 50)}/100"

                # 🔊 Volumen maestro real (COM propio de este hilo)
                try:
                    from comtypes import CoInitialize, CoUninitialize
                    from pycaw.pycaw import AudioUtilities
                    CoInitialize()
                    try:
                        v = AudioUtilities.GetSpeakers().EndpointVolume.GetMasterVolumeLevelScalar()
                        datos["volumen"] = int(round(v * 100))
                    finally:
                        CoUninitialize()
                except Exception:
                    pass
            except Exception:
                pass

            self._stats_lentas = datos
            time.sleep(10)

    def apply_new_theme(self, theme_name):
        set_global_theme(theme_name)
        self.orb._safe_sync_theme()

    def _open_settings(self):
        dialog = DeviceSettingsDialog(self)
        dialog.exec()

class MockRoot:
    def __init__(self, qapp: QApplication): self.qapp = qapp
    def mainloop(self): sys.exit(self.qapp.exec())

class Comunicador(QObject):
    senal_estado = pyqtSignal(str)
    senal_log = pyqtSignal(str)
    senal_transcripcion = pyqtSignal(str)
    senal_usuario = pyqtSignal(str)   # transcripción de TU voz (burbujas del diálogo)
    senal_voz = pyqtSignal(float)     # nivel de la voz de I.R.I.S. (animación al hablar)

class JarvisUI:
    def __init__(self, face_path=""):
        try:
            cfg = load_api_keys()
            saved_theme = cfg.get("jarvis_theme", "green")
            set_global_theme(saved_theme)
        except Exception:
            pass

        self.app = QApplication.instance() or QApplication(sys.argv)
        self.root = MockRoot(self.app)
        self.muted = False
        self._win = MainWindow(self, face_path)

        self.puente = Comunicador()
        self.puente.senal_estado.connect(self.set_state)
        self.puente.senal_log.connect(self.write_log)
        self.puente.senal_transcripcion.connect(self.escribir_holograma)
        self.puente.senal_usuario.connect(self.escribir_usuario)
        self.puente.senal_voz.connect(self._win.orb.set_voice)

        # 🟢 MAGIA: Forzamos la apertura en Pantalla Completa Absoluta
        self._win.showFullScreen()

    def set_state(self, state_text):
        # Estado canónico para la animación del núcleo
        if "VENTANA" in state_text:
            self._win.orb.set_state("WINDOW")
        elif "GRABANDO" in state_text:
            self._win.orb.set_state("ENROLLING")
        elif "ESCUCHANDO" in state_text or "EN LÍNEA" in state_text:
            self._win.orb.set_state("LISTENING")
        elif "HABLANDO" in state_text:
            self._win.orb.set_state("SPEAKING")
        else:
            self._win.orb.set_state("IDLE")
        # Y el texto tal cual (sin emojis) en el chip de estado
        limpio = "".join(c for c in state_text if c.isalnum() or c.isspace() or c in "ÁÉÍÓÚÑáéíóúñ.").strip()
        if limpio:
            self._win.orb._js(f"if (window.updateStatusText) window.updateStatusText({json.dumps(limpio.upper())});")

    def write_log(self, text):
        self._win.orb._js(f"if (window.updateConsole) window.updateConsole({json.dumps(text)});")

    def escribir_holograma(self, text):
        clean_text = text.replace("IRIS:", "").replace("JARVIS:", "").strip()
        self._win.orb._js(f"if (window.updateChat) window.updateChat('iris', {json.dumps(clean_text)});")

    def escribir_usuario(self, text):
        limpio = (text or "").strip()
        if limpio:
            self._win.orb._js(f"if (window.updateChat) window.updateChat('user', {json.dumps(limpio)});")

if __name__ == "__main__":
    ui = JarvisUI()
    ui.root.mainloop()
