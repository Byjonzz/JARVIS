"""ui.py — I.R.I.S. Pure WebGL HUD Interface (FULLSCREEN)"""
from __future__ import annotations
import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, pyqtSlot, QObject, QTimer
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

from settings_window import DeviceSettingsDialog

try:
    from config_manager import load_api_keys
except ImportError:
    def load_api_keys(): return {}

_BA_TZ = timezone(timedelta(hours=-6))

THEMES = {
    "green": {"PRI": "#00FF00", "PRI_DIM": "#00CC00", "BG": "#000000", "TEXT": "#FFFFFF", "BORDER": "rgba(0, 255, 0, 0.45)"},
    "cyan": {"PRI": "#00FFFF", "PRI_DIM": "#00CCCC", "BG": "#000000", "TEXT": "#FFFFFF", "BORDER": "rgba(0, 255, 255, 0.45)"},
    "red": {"PRI": "#FF0000", "PRI_DIM": "#CC0000", "BG": "#000000", "TEXT": "#FFFFFF", "BORDER": "rgba(255, 0, 0, 0.45)"},
    "purple": {"PRI": "#9D00FF", "PRI_DIM": "#7A00CC", "BG": "#000000", "TEXT": "#FFFFFF", "BORDER": "rgba(157, 0, 255, 0.45)"},
    "gold": {"PRI": "#f59e0b", "PRI_DIM": "#d97706", "BG": "#0c0804", "TEXT": "#fde68a", "BORDER": "rgba(245, 158, 11, 0.45)"},
    "white": {"PRI": "#FFFFFF", "PRI_DIM": "#CCCCCC", "BG": "#000000", "TEXT": "#FFFFFF", "BORDER": "rgba(255, 255, 255, 0.45)"}
}

C_PRI = THEMES["green"]["PRI"]
C_PRI_DIM = THEMES["green"]["PRI_DIM"]
C_TEXT = THEMES["green"]["TEXT"]
C_BORDER = THEMES["green"]["BORDER"]

def set_global_theme(theme_name):
    global C_PRI, C_PRI_DIM, C_TEXT, C_BORDER
    t = THEMES.get(theme_name, THEMES["green"])
    C_PRI = t["PRI"]
    C_PRI_DIM = t["PRI_DIM"]
    C_TEXT = t["TEXT"]
    C_BORDER = t["BORDER"]

class WebBridge(QObject):
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

    @pyqtSlot(int, int)
    def move_window(self, dx, dy):
        pass # Desactivado porque ahora estamos en pantalla completa absoluta

class CustomParticleOrb(QWidget):
    audio_signal = pyqtSignal(float)
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
        
        sphere_path = Path(__file__).parent / "assets" / "sphere.html"
        self.web_view.setUrl(QUrl.fromLocalFile(str(sphere_path.absolute())))
        layout.addWidget(self.web_view)
        
        self.audio_signal.connect(self._safe_set_audio)
        self.state_signal.connect(self._safe_set_state)
        self.theme_signal.connect(self._safe_sync_theme)
        self.web_view.loadFinished.connect(self._on_load_finished)
        
    def _on_load_finished(self, ok):
        if ok:
            self.sync_theme()
            self.set_state("LISTENING")

    def sync_theme(self): self.theme_signal.emit()
    def set_audio(self, level: float): self.audio_signal.emit(level)
    def set_state(self, state: str): self.state_signal.emit(state)

    def _safe_sync_theme(self):
        colors = {'PRI': C_PRI, 'PRI_DIM': C_PRI_DIM, 'TEXT': C_TEXT, 'BORDER': C_BORDER}
        self.web_view.page().runJavaScript(f"if (window.setThemeColors) window.setThemeColors({json.dumps(colors)});")

    def _safe_set_audio(self, level: float):
        self.web_view.page().runJavaScript(f"if (window.updateVolume) window.updateVolume({level});")

    def _safe_set_state(self, state: str):
        self.web_view.page().runJavaScript(f"if (window.updateState) window.updateState('{state}');")

class MainWindow(QMainWindow):
    def __init__(self, ui, face_path):
        super().__init__()
        self.ui = ui
        self.ui._win = self
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: black;")
        
        self.orb = CustomParticleOrb(self.ui, self)
        self.setCentralWidget(self.orb)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()

    def tick(self):
        try:
            now = datetime.now(_BA_TZ)
            time_str = now.strftime("%I:%M:%S %p")
            date_str = now.strftime("%A, %d %B %Y").upper()
            js_code = f"if (window.updateClock) window.updateClock('{time_str}', '{date_str}');"
            self.orb.web_view.page().runJavaScript(js_code)
        except Exception:
            pass

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
        
        # 🟢 MAGIA: Forzamos la apertura en Pantalla Completa Absoluta
        self._win.showFullScreen()
        
    def set_state(self, state_text):
        if ("ESCUCHANDO" in state_text or "EN LÍNEA" in state_text
                or "VENTANA" in state_text or "GRABANDO" in state_text):
            self._win.orb.set_state("LISTENING")
        elif "HABLANDO" in state_text:
            self._win.orb.set_state("SPEAKING")
        else:
            self._win.orb.set_state("IDLE")
            
    def write_log(self, text):
        js_code = f"if (window.updateConsole) window.updateConsole({json.dumps(text)});"
        self._win.orb.web_view.page().runJavaScript(js_code)

    def escribir_holograma(self, text):
        clean_text = text.replace("IRIS:", "").replace("JARVIS:", "").strip()
        js_code = f"if (window.updateConsole) window.updateConsole({json.dumps(clean_text)});"
        self._win.orb.web_view.page().runJavaScript(js_code)

if __name__ == "__main__":
    ui = JarvisUI()
    ui.root.mainloop()