"""ui.py — 100% Custom Gold-Themed Dynamic Bento PyQt6 User Interface for JARVIS."""
from __future__ import annotations
import sys
import os
import json
import psutil
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGridLayout, QLabel, QPushButton, QLineEdit, QTextEdit, 
    QListWidget, QListWidgetItem, QProgressBar
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, pyqtSlot, QObject, QTimer
from PyQt6.QtGui import QFont, QIcon, QMouseEvent
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

# --- NUEVOS MÓDULOS DE JARVIS ---
from settings_window import DeviceSettingsDialog
from camera_hud import CameraPreviewWindow
from alerts import JarvisMessageBox

try:
    import qtawesome as qta
    HAS_QTA = True
except ImportError:
    HAS_QTA = False

# Zona Horaria (Ajustable a tu región)
_BA_TZ = timezone(timedelta(hours=-6)) # Ajustado a México (GMT-6)

# Theme Tokens (Gold)
C_PRI = "#f59e0b"
C_PRI_DIM = "#78350f"
C_BG = "#0c0804"
C_PANEL = "rgba(35, 28, 10, 0.60)" # Cajas Bento translúcidas
C_BORDER = "rgba(245, 158, 11, 0.45)"
C_TEXT = "#fde68a"
RED = "#ff3b30"


class WebBridge(QObject):
    def __init__(self, orb):
        super().__init__()
        self.orb = orb

    @pyqtSlot()
    def toggle_mute(self):
        if self.orb.ui: self.orb.ui._win._toggle_mute()

    @pyqtSlot()
    def request_theme(self):
        QTimer.singleShot(0, self.orb.sync_theme)


class CustomParticleOrb(QWidget):
    audio_signal = pyqtSignal(float)
    state_signal = pyqtSignal(str)
    theme_signal = pyqtSignal()

    def __init__(self, ui, parent=None):
        super().__init__(parent)
        self.ui = ui
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.web_view = QWebEngineView(self)
        self.web_view.setStyleSheet("background: transparent;")
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)
        
        try:
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            settings = self.web_view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        except Exception as e:
            print(f"[ORB] Settings Error: {e}")
            
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
            self.set_state("MUTED" if self.ui.muted else "LISTENING")

    def sync_theme(self): self.theme_signal.emit()
    def set_audio(self, level: float): self.audio_signal.emit(level)
    def set_state(self, state: str): self.state_signal.emit(state)

    def _safe_sync_theme(self):
        colors = {'PRI': C_PRI, 'PRI_DIM': C_PRI_DIM, 'TEXT': C_TEXT, 'BG': C_BG}
        self.web_view.page().runJavaScript(f"if (window.setThemeColors) window.setThemeColors({json.dumps(colors)});")

    def _safe_set_audio(self, level: float):
        self.web_view.page().runJavaScript(f"if (window.updateVolume) window.updateVolume({level});")

    def _safe_set_state(self, state: str):
        self.web_view.page().runJavaScript(f"if (window.updateState) window.updateState('{state}');")


class ClockWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ClockWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_time = QLabel("12:00:00")
        font_t = QFont("Century Gothic", 28, QFont.Weight.Bold)
        font_t.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        self.lbl_time.setFont(font_t)
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.lbl_time)
        
        self.lbl_date = QLabel("Cargando fecha...")
        self.lbl_date.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.lbl_date)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()
        self.update_style()
        
    def tick(self):
        try:
            now = datetime.now(_BA_TZ)
            self.lbl_time.setText(now.strftime("%I:%M:%S %p"))
            self.lbl_date.setText(now.strftime("%A, %d %B %Y"))
            
        except Exception as e:
            print(f"[ClockWidget] Error updating time: {e}")

    def update_style(self):
        self.setStyleSheet("QWidget#ClockWidget { background: transparent; border: none; }")
        self.lbl_time.setStyleSheet("color: white; border: none; background: transparent;")
        self.lbl_date.setStyleSheet(f"font-size: 13px; letter-spacing: 1px; color: {C_PRI}; border: none; font-weight: bold; background: transparent;")


class WeatherWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WeatherWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        
        header = QHBoxLayout()
        self.lbl_title = QLabel("WEATHER REPORT")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        info = QHBoxLayout()
        self.lbl_temp = QLabel("18°C")
        self.lbl_desc = QLabel("Parcialmente Nublado")
        info.addWidget(self.lbl_temp)
        info.addWidget(self.lbl_desc)
        info.addStretch()
        layout.addLayout(info)
        layout.addStretch()
        
        self.update_style()
        
    def update_style(self):
        self.setStyleSheet(f"QWidget#WeatherWidget {{ background: {C_PANEL}; border: 1.5px solid {C_BORDER}; border-radius: 12px; }}")
        self.lbl_title.setStyleSheet(f"font-weight: bold; font-size: 11px; letter-spacing: 2px; color: {C_PRI}; background: transparent; border: none;")
        self.lbl_temp.setStyleSheet("font-size: 26px; font-weight: bold; color: white; background: transparent; border: none; margin-right: 10px;")
        self.lbl_desc.setStyleSheet(f"font-size: 12px; color: {C_TEXT}; background: transparent; border: none;")


class SpotifyWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SpotifyWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        
        header = QHBoxLayout()
        self.lbl_title = QLabel("SPOTIFY CONTROL")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        self.lbl_track = QLabel("Not Playing")
        self.lbl_artist = QLabel("Awaiting tracks...")
        layout.addWidget(self.lbl_track)
        layout.addWidget(self.lbl_artist)
        
        controls = QHBoxLayout()
        self.btn_prev = QPushButton("⏮")
        self.btn_play = QPushButton("▶")
        self.btn_next = QPushButton("⏭")
        
        for btn in (self.btn_prev, self.btn_play, self.btn_next):
            btn.setFixedSize(35, 35)
            controls.addWidget(btn)
        controls.addStretch()
        layout.addLayout(controls)
        
        self.btn_play.clicked.connect(lambda: threading.Thread(target=self._press, args=("playpause",), daemon=True).start())
        self.btn_next.clicked.connect(lambda: threading.Thread(target=self._press, args=("nexttrack",), daemon=True).start())
        self.btn_prev.clicked.connect(lambda: threading.Thread(target=self._press, args=("prevtrack",), daemon=True).start())

        self.update_style()
        
    def _press(self, key):
        try:
            import pyautogui
            pyautogui.press(key)
        except Exception as e:
            print(f"[Spotify] Error de control local: {e}")

    def update_style(self):
        self.setStyleSheet(f"QWidget#SpotifyWidget {{ background: {C_PANEL}; border: 1.5px solid {C_BORDER}; border-radius: 12px; }}")
        self.lbl_title.setStyleSheet(f"font-weight: bold; font-size: 11px; letter-spacing: 2px; color: {C_PRI}; background: transparent; border:none;")
        self.lbl_track.setStyleSheet("font-size: 16px; font-weight: bold; color: white; background: transparent; border:none; margin-top: 5px;")
        self.lbl_artist.setStyleSheet(f"font-size: 12px; color: {C_PRI_DIM}; background: transparent; border:none; margin-bottom: 5px;")
        
        btn_style = f"QPushButton {{ background: rgba(245,158,11,0.1); border: 1px solid {C_BORDER}; border-radius: 17px; color: white; font-size: 16px; }} QPushButton:hover {{ background: rgba(245,158,11,0.3); border-color: {C_PRI}; }}"
        self.btn_play.setStyleSheet(btn_style)
        self.btn_next.setStyleSheet(btn_style)
        self.btn_prev.setStyleSheet(btn_style)


class SystemWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SystemWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        
        header = QHBoxLayout()
        self.lbl_title = QLabel("SYSTEM GAUGES")
        header.addWidget(self.lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        self.cpu_bar = QProgressBar()
        self.ram_bar = QProgressBar()
        
        self.lbl_cpu = QLabel("CPU Status")
        layout.addWidget(self.lbl_cpu)
        layout.addWidget(self.cpu_bar)
        
        self.lbl_ram = QLabel("RAM Status")
        layout.addWidget(self.lbl_ram)
        layout.addWidget(self.ram_bar)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(1500) 
        self.update_style()
        
    def update_stats(self):
        try:
            self.cpu_bar.setValue(int(psutil.cpu_percent()))
            self.ram_bar.setValue(int(psutil.virtual_memory().percent))
        except Exception as e:
            print(f"[System] Error sensor: {e}")

    def update_style(self):
        self.setStyleSheet(f"QWidget#SystemWidget {{ background: {C_PANEL}; border: 1.5px solid {C_BORDER}; border-radius: 12px; }}")
        self.lbl_title.setStyleSheet(f"font-weight: bold; font-size: 11px; letter-spacing: 2px; color: {C_PRI}; border:none; background: transparent;")
        lbl_style = f"font-size: 11px; color: {C_TEXT}; border: none; background: transparent; margin-top: 5px;"
        self.lbl_cpu.setStyleSheet(lbl_style)
        self.lbl_ram.setStyleSheet(lbl_style)
        
        bar_style = f"QProgressBar {{ border: 1px solid {C_BORDER}; border-radius: 6px; text-align: center; color: white; height: 16px; background: rgba(0,0,0,0.4); }} QProgressBar::chunk {{ background-color: {C_PRI}; border-radius: 5px; }}"
        self.cpu_bar.setStyleSheet(bar_style)
        self.ram_bar.setStyleSheet(bar_style)


class TodoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TodoWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        
        self.lbl_title = QLabel("TODOS")
        layout.addWidget(self.lbl_title)
        
        inp_layout = QHBoxLayout()
        self.txt_task = QLineEdit()
        self.txt_task.setPlaceholderText("New chore...")
        self.btn_add = QPushButton("+")
        self.btn_add.setFixedSize(30, 30)
        inp_layout.addWidget(self.txt_task)
        inp_layout.addWidget(self.btn_add)
        layout.addLayout(inp_layout)
        
        self.lst_todo = QListWidget()
        layout.addWidget(self.lst_todo)
        
        self.btn_add.clicked.connect(self.add_task)
        self.txt_task.returnPressed.connect(self.add_task)
        self.update_style()
        
    def add_task(self):
        text = self.txt_task.text().strip()
        if text:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.lst_todo.addItem(item)
            self.txt_task.clear()

    def update_style(self):
        self.setStyleSheet(f"QWidget#TodoWidget {{ background: {C_PANEL}; border: 1.5px solid {C_BORDER}; border-radius: 12px; }}")
        self.lbl_title.setStyleSheet(f"font-weight: bold; font-size: 11px; letter-spacing: 2px; color: {C_PRI}; border: none; background: transparent;")
        self.txt_task.setStyleSheet(f"QLineEdit {{ background: rgba(0,0,0,0.5); border: 1px solid {C_BORDER}; border-radius: 6px; padding: 6px; color: white; }}")
        self.btn_add.setStyleSheet(f"QPushButton {{ background: {C_PRI}; color: black; font-weight: bold; border-radius: 6px; font-size: 18px; }}")
        self.lst_todo.setStyleSheet("QListWidget { border: none; background: transparent; } QListWidget::item { color: white; margin-top: 5px; }")


class NotesWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NotesWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        
        self.lbl_title = QLabel("PAD NOTES")
        layout.addWidget(self.lbl_title)
        
        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText("Write details...")
        layout.addWidget(self.txt_notes)
        self.update_style()

    def update_style(self):
        self.setStyleSheet(f"QWidget#NotesWidget {{ background: {C_PANEL}; border: 1.5px solid {C_BORDER}; border-radius: 12px; }}")
        self.lbl_title.setStyleSheet(f"font-weight: bold; font-size: 11px; letter-spacing: 2px; color: {C_PRI}; border: none; background: transparent;")
        self.txt_notes.setStyleSheet(f"QTextEdit {{ border: none; background: rgba(0,0,0,0.4); border-radius: 6px; padding: 8px; color: white; font-size: 13px; }}")


class FilesPanel(QWidget):
    def __init__(self, ui, parent=None):
        super().__init__(parent)
        self.ui = ui
        self.setObjectName("FilesPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        
        self.lbl_title = QLabel("FILES DROP")
        layout.addWidget(self.lbl_title)
        
        self.drop_zone = QLabel("Drop File Trigger\n\n(Arrastra archivos aquí)")
        self.drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.drop_zone)
        
        self.update_style()

    def update_style(self):
        self.setStyleSheet(f"QWidget#FilesPanel {{ background: {C_PANEL}; border: 1.5px solid {C_BORDER}; border-radius: 12px; }}")
        self.lbl_title.setStyleSheet(f"font-weight: bold; font-size: 11px; letter-spacing: 2px; color: {C_PRI}; border: none; background: transparent;")
        self.drop_zone.setStyleSheet(f"QLabel {{ background: rgba(0,0,0,0.4); border: 2px dashed {C_BORDER}; border-radius: 8px; color: {C_TEXT}; font-weight: bold; padding: 15px; }}")


class MainWindow(QMainWindow):
    _shutdown_sig = pyqtSignal()

    def __init__(self, ui, face_path):
        super().__init__()
        self.ui = ui
        self.ui._win = self
        
        self.resize(1150, 800)
        self.setMinimumSize(1000, 750)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) 
        
        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("centralWidget")
        self.setCentralWidget(self.central_widget)
        
        self.lbl_brand = QLabel("J A R V I S", self.central_widget)
        font = QFont("Century Gothic", 20, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 10.0)
        self.lbl_brand.setFont(font)
        
        self.btn_close = QPushButton("✖", self.central_widget)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)
        
        # --- NUEVOS BOTONES DE HEADER ---
        self.btn_settings = QPushButton("⚙️", self.central_widget)
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(self._open_settings)
        
        self.btn_camera = QPushButton("🎥", self.central_widget)
        self.btn_camera.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_camera.clicked.connect(self._toggle_camera)
        
        self.orb = CustomParticleOrb(self.ui, self.central_widget)
        
        self.bento_container = QWidget(self.central_widget)
        bento_layout = QGridLayout(self.bento_container)
        bento_layout.setContentsMargins(0, 0, 0, 0)
        bento_layout.setSpacing(15)
        
        self.spotify_w = SpotifyWidget()
        self.weather_w = WeatherWidget()
        self.system_w = SystemWidget()
        self.todo_w = TodoWidget()
        self.notes_w = NotesWidget()
        self.files_panel = FilesPanel(self.ui)
        
        bento_layout.addWidget(self.spotify_w, 0, 0, 1, 2)
        bento_layout.addWidget(self.weather_w, 0, 2, 1, 1)
        bento_layout.addWidget(self.system_w, 0, 3, 1, 1)
        bento_layout.addWidget(self.todo_w, 1, 0, 1, 1)
        bento_layout.addWidget(self.notes_w, 1, 1, 1, 2)
        bento_layout.addWidget(self.files_panel, 1, 3, 1, 1)
        
        bento_layout.setColumnStretch(0, 1)
        bento_layout.setColumnStretch(1, 1)
        bento_layout.setColumnStretch(2, 1)
        bento_layout.setColumnStretch(3, 1)
        
        self.clock_w = ClockWidget(self.central_widget)
        
        self.txt_console = QLabel(self.central_widget)
        self.txt_console.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.update_theme_styles()
        self._drag_pos = None

    def update_theme_styles(self):
        self.central_widget.setStyleSheet(f"QWidget#centralWidget {{ background-color: #080502; background: radial-gradient(circle at center, #1f1406 0%, #080502 80%); border: 2.2px solid {C_PRI}; border-radius: 20px; }}")
        self.lbl_brand.setStyleSheet(f"color: {C_PRI}; background: transparent; border: none;")
        
        btn_style = f"QPushButton {{ color: {C_PRI}; background: rgba(245,158,11,0.1); border: 1px solid {C_BORDER}; border-radius: 15px; font-size: 16px; font-weight: bold; }} QPushButton:hover {{ background: {RED}; color: white; border-color: {RED}; }}"
        self.btn_close.setStyleSheet(btn_style)
        self.btn_settings.setStyleSheet(btn_style)
        self.btn_camera.setStyleSheet(btn_style)
        
        self.txt_console.setStyleSheet(f"QLabel {{ color: {C_PRI}; font-weight: bold; font-size: 16px; background: transparent; }}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        W, H = self.central_widget.width(), self.central_widget.height()
        
        self.lbl_brand.setGeometry(25, 20, 250, 40)
        self.btn_close.setGeometry(W - 55, 20, 30, 30)
        
        self.btn_settings.setGeometry(W - 95, 20, 30, 30)
        self.btn_camera.setGeometry(W - 135, 20, 30, 30)
        
        self.clock_w.setGeometry(W - 280, 70, 250, 80)
        self.orb.setGeometry(0, 50, W, H - 50)
        self.txt_console.setGeometry(30, H - 50, W - 60, 40)
        
        bh = H // 2 - 20 
        self.bento_container.setGeometry(25, H - bh - 60, W - 50, bh)
        
        self.bento_container.raise_()
        self.txt_console.raise_()
        self.clock_w.raise_()

    def _open_settings(self):
        dialog = DeviceSettingsDialog(self)
        dialog.exec()

    def _toggle_camera(self):
        if not hasattr(self, 'camera_window') or self.camera_window is None:
            self.camera_window = CameraPreviewWindow(parent=None)
            self.camera_window.show()
            self.camera_window.move(50, 50)
        else:
            if self.camera_window.isVisible():
                self.camera_window.hide()
            else:
                self.camera_window.show()
                self.camera_window.raise_()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)


class MockRoot:
    def __init__(self, qapp: QApplication): self.qapp = qapp
    def mainloop(self): sys.exit(self.qapp.exec())

class Comunicador(QObject):
    senal_estado = pyqtSignal(str)
    senal_log = pyqtSignal(str)
    senal_transcripcion = pyqtSignal(str)

class JarvisUI:
    def __init__(self, face_path=""):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.root = MockRoot(self.app)
        self.muted = False
        self._win = MainWindow(self, face_path)
        
        # --- EL PUENTE RESTAURADO ---
        self.puente = Comunicador()
        self.puente.senal_estado.connect(self.set_state)
        self.puente.senal_log.connect(self.write_log)
        self.puente.senal_transcripcion.connect(self.escribir_holograma)
        
        self._win.show()
        
    def set_state(self, state_text):
        if "EN LÍNEA" in state_text:
            self._win.orb.set_state("LISTENING")
            
    def write_log(self, text):
        self._win.txt_console.setText(text)

    def escribir_holograma(self, text):
        # Escribe los subtítulos de lo que JARVIS va diciendo
        self._win.txt_console.setText(text)

    def clear_jarvis_response(self):
        self._win.txt_console.setText("")

    def stream_jarvis_chunk(self, chunk: str):
        self._win.txt_console.setText(chunk.replace("JARVIS:", "").strip())

if __name__ == "__main__":
    ui = JarvisUI()
    ui.root.mainloop()