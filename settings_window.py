import os
import threading
import webbrowser
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

import sounddevice as sd

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QComboBox, QCheckBox, QScrollArea, QFrame, QSlider, QWidget
)
from PyQt6.QtCore import Qt, QTimer

from alerts import JarvisMessageBox

# 🟢 Usando el gestor correcto
from config_manager import load_api_keys, save_api_keys

C_PRI = "#f59e0b"
C_BG = "#0c0804"
C_BORDER = "rgba(245, 158, 11, 0.45)"
C_TEXT = "#fde68a"

THEMES_KEYS = ["cyan", "green", "red", "purple", "gold", "white"]

class DeviceSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JARVIS Settings Configuration Control")
        self.resize(580, 680)
        self.update_style()
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        scroll = QScrollArea(self)
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea#settingsScroll { background: transparent; } QScrollArea#settingsScroll > QWidget { background: transparent; }")
        main_layout.addWidget(scroll)
        
        content_w = QWidget()
        content_w.setObjectName("settingsContent")
        content_w.setStyleSheet("QWidget#settingsContent { background: transparent; }")
        layout = QVBoxLayout(content_w)
        layout.setSpacing(10)
        layout.setContentsMargins(5, 5, 5, 5)
        scroll.setWidget(content_w)
        
        layout.addWidget(QLabel(f"<h2 style='color: {C_PRI}; font-family: sans-serif; margin-bottom: 5px;'>System Master Configurations</h2>"))
        
        layout.addWidget(QLabel("Gemini API Key:"))
        self.inp_gemini = QLineEdit()
        self.inp_gemini.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.inp_gemini)
        
        layout.addWidget(QLabel("OpenRouter API Key:"))
        self.inp_openrouter = QLineEdit()
        self.inp_openrouter.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.inp_openrouter)
        
        layout.addWidget(QLabel("AI Provider / Brain System:"))
        self.cmb_ai_provider = QComboBox()
        self.cmb_ai_provider.addItem("Google Gemini (Cloud realtime)", "gemini")
        self.cmb_ai_provider.addItem("OpenRouter (Cloud fallback)", "openrouter")
        self.cmb_ai_provider.addItem("Ollama (Local Offline AI)", "ollama")
        layout.addWidget(self.cmb_ai_provider)
        
        self.ollama_url_lbl = QLabel("Ollama Server URL (Local AI):")
        layout.addWidget(self.ollama_url_lbl)
        self.inp_ollama_url = QLineEdit()
        self.inp_ollama_url.setPlaceholderText("http://127.0.0.1:11434")
        layout.addWidget(self.inp_ollama_url)
        
        self.ollama_model_lbl = QLabel("Ollama Model Name:")
        layout.addWidget(self.ollama_model_lbl)
        self.inp_ollama_model = QLineEdit()
        self.inp_ollama_model.setPlaceholderText("gemma2:2b (or llama3, phi3)")
        layout.addWidget(self.inp_ollama_model)
        
        self.cmb_ai_provider.currentIndexChanged.connect(self._toggle_ollama_fields)
        
        layout.addWidget(QLabel("Active Voice Model:"))
        self.cmb_voice = QComboBox()
        self.voices = [
            ("Aoede", "Femenina (Cálida y sofisticada ✨)"), ("Kore", "Femenina (Suave y precisa)"),
            ("Leda", "Femenina (Natural y fluida)"), ("Zephyr", "Femenina (Dinámica y expresiva)"),
            ("Charon", "Masculina (Profunda y seria)"), ("Puck", "Masculina (Ágil y versátil)"),
            ("Fenrir", "Masculina (Grave y autoritaria)"), ("Orus", "Masculina (Clásica y equilibrada)")
        ]
        for val, desc in self.voices:
            self.cmb_voice.addItem(desc, val)
        layout.addWidget(self.cmb_voice)
        
        layout.addWidget(QLabel("Theme Palette Scheme:"))
        self.cmb_theme = QComboBox()
        for k in THEMES_KEYS:
            self.cmb_theme.addItem(k.upper(), k)
        layout.addWidget(self.cmb_theme)
        
        layout.addWidget(QLabel("Nombre del Usuario (¿Cómo desea que lo llame?):"))
        self.inp_user_name = QLineEdit()
        self.inp_user_name.setPlaceholderText("Ej: Señor Leguion")
        layout.addWidget(self.inp_user_name)
        
        layout.addWidget(QLabel("Microphone Input Device:"))
        self.cmb_mic = QComboBox()
        layout.addWidget(self.cmb_mic)

        layout.addWidget(QLabel(f"<hr style='border: 0; border-top: 1px solid {C_BORDER}; margin: 5px 0;'>"))
        sens_layout = QHBoxLayout()
        sens_layout.addWidget(QLabel("Sensibilidad del Micrófono (Software Gain):"))
        self.lbl_mic_sens_val = QLabel("50%")
        self.lbl_mic_sens_val.setStyleSheet(f"font-weight: bold; color: {C_PRI};")
        sens_layout.addStretch()
        sens_layout.addWidget(self.lbl_mic_sens_val)
        layout.addLayout(sens_layout)

        self.sld_mic_sens = QSlider(Qt.Orientation.Horizontal)
        self.sld_mic_sens.setRange(0, 100)
        self.sld_mic_sens.setValue(50)
        
        self.sld_mic_sens.valueChanged.connect(lambda v: self.lbl_mic_sens_val.setText(f"{v}%"))
        layout.addWidget(self.sld_mic_sens)
        
        layout.addWidget(QLabel("Speaker Output Device:"))
        self.cmb_speaker = QComboBox()
        layout.addWidget(self.cmb_speaker)

        layout.addWidget(QLabel("Active Camera Device (Gesture Pilot):"))
        self.cmb_camera = QComboBox()
        layout.addWidget(self.cmb_camera)
        
        layout.addWidget(QLabel("DroidCam IP Address or URL (Optional):"))
        self.inp_camera_ip = QLineEdit()
        self.inp_camera_ip.setPlaceholderText("Ej: 192.168.1.50 (o http://192.168.1.50:4747/video)")
        layout.addWidget(self.inp_camera_ip)
        
        layout.addWidget(QLabel(f"<hr style='border: 0; border-top: 1px solid {C_BORDER}; margin: 8px 0;'><h3 style='color: {C_PRI}; font-family: sans-serif; margin: 0;'>Resource & Visual Management</h3>"))
        perf_layout = QHBoxLayout()
        perf_layout.addWidget(QLabel("Visual Performance Quality (Caps RAM/GPU):"))
        self.lbl_performance_val = QLabel("80%")
        self.lbl_performance_val.setStyleSheet("font-weight: bold; color: #00ff88;")
        perf_layout.addStretch()
        perf_layout.addWidget(self.lbl_performance_val)
        layout.addLayout(perf_layout)
        
        self.sld_performance = QSlider(Qt.Orientation.Horizontal)
        self.sld_performance.setRange(1, 100)
        self.sld_performance.setValue(80)
        self.sld_performance.valueChanged.connect(lambda v: self.lbl_performance_val.setText(f"{v}%"))
        layout.addWidget(self.sld_performance)
        
        self.chk_gpu = QCheckBox("Enable GPU Rendering Acceleration")
        layout.addWidget(self.chk_gpu)
        
        layout.addWidget(QLabel(f"<hr style='border: 0; border-top: 1px solid {C_BORDER}; margin: 8px 0;'><h3 style='color: {C_PRI}; font-family: sans-serif; margin: 0;'>Spotify Integration</h3>"))
        
        self.chk_advanced_spotify = QCheckBox("Configuración de desarrollador avanzada (Opcional)")
        layout.addWidget(self.chk_advanced_spotify)
        
        self.spotify_id_lbl = QLabel("Spotify Client ID:")
        layout.addWidget(self.spotify_id_lbl)
        self.inp_spotify_id = QLineEdit()
        layout.addWidget(self.inp_spotify_id)
        
        self.spotify_secret_lbl = QLabel("Spotify Client Secret:")
        layout.addWidget(self.spotify_secret_lbl)
        self.inp_spotify_secret = QLineEdit()
        self.inp_spotify_secret.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.inp_spotify_secret)
        
        self.spotify_uri_lbl = QLabel("Spotify Redirect URI:")
        layout.addWidget(self.spotify_uri_lbl)
        self.inp_spotify_uri = QLineEdit()
        self.inp_spotify_uri.setText("http://127.0.0.1:8888/callback")
        layout.addWidget(self.inp_spotify_uri)
        
        self.chk_advanced_spotify.toggled.connect(self._toggle_advanced_spotify)
        
        spotify_auth_layout = QHBoxLayout()
        self.btn_spotify_login = QPushButton("Conectar con Spotify (Google/Email)")
        self.lbl_spotify_status = QLabel("Consultando estado...")
        self.lbl_spotify_status.setStyleSheet("color: #a3a3a3; font-style: italic;")
        spotify_auth_layout.addWidget(self.btn_spotify_login)
        spotify_auth_layout.addWidget(self.lbl_spotify_status)
        layout.addLayout(spotify_auth_layout)
        
        self.btn_spotify_login.clicked.connect(self.connect_spotify)
        
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Save Configurations")
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)
        
        self.btn_save.clicked.connect(self.save)

        # 1. Escanear Hardware
        self.poblar_dispositivos_hardware()
        
        # 2. Cargar Selecciones
        self.load_settings()

    def poblar_dispositivos_hardware(self):
        self.cmb_mic.clear()
        self.cmb_speaker.clear()
        self.cmb_camera.clear()

        # 🟢 Lector de Audio Nativo y Limpio (Sin choques)
        try:
            dispositivos_audio = sd.query_devices()
            mic_agregados = set()
            spk_agregados = set()
            
            for dev in dispositivos_audio:
                nombre = dev['name']
                if dev['max_input_channels'] > 0 and nombre not in mic_agregados:
                    self.cmb_mic.addItem(nombre)
                    mic_agregados.add(nombre)
                
                if dev['max_output_channels'] > 0 and nombre not in spk_agregados:
                    self.cmb_speaker.addItem(nombre)
                    spk_agregados.add(nombre)
                    
            if self.cmb_mic.count() == 0: self.cmb_mic.addItem("Default Microphone")
            if self.cmb_speaker.count() == 0: self.cmb_speaker.addItem("Default Speaker")
        except Exception:
            self.cmb_mic.addItem("Default Microphone")
            self.cmb_speaker.addItem("Default Speaker")

        try:
            from PyQt6.QtMultimedia import QMediaDevices
            camaras = QMediaDevices.videoInputs()
            if camaras:
                for cam in camaras:
                    self.cmb_camera.addItem(cam.description())
            else:
                self.cmb_camera.addItem("No se encontraron cámaras")
        except ImportError:
            self.cmb_camera.addItem("Cámara Principal (Default)")
            self.cmb_camera.addItem("Cámara Secundaria (USB)")
            self.cmb_camera.addItem("Cámara Virtual (OBS/DroidCam)")

    def _toggle_ollama_fields(self):
        is_ollama = (self.cmb_ai_provider.currentData() == "ollama")
        self.ollama_url_lbl.setVisible(is_ollama)
        self.inp_ollama_url.setVisible(is_ollama)
        self.ollama_model_lbl.setVisible(is_ollama)
        self.inp_ollama_model.setVisible(is_ollama)

    def _toggle_advanced_spotify(self, checked):
        self.spotify_id_lbl.setVisible(checked)
        self.inp_spotify_id.setVisible(checked)
        self.spotify_secret_lbl.setVisible(checked)
        self.inp_spotify_secret.setVisible(checked)
        self.spotify_uri_lbl.setVisible(checked)
        self.inp_spotify_uri.setVisible(checked)

    def load_settings(self):
        try:
            cfg = load_api_keys()
            self.inp_gemini.setText(cfg.get("gemini_api_key", ""))
            self.inp_openrouter.setText(cfg.get("openrouter_api_key", ""))
            
            prov = cfg.get("ai_provider", "gemini")
            idx = self.cmb_ai_provider.findData(prov)
            if idx >= 0: self.cmb_ai_provider.setCurrentIndex(idx)
            
            self.inp_user_name.setText(cfg.get("user_name", ""))
            self.inp_camera_ip.setText(cfg.get("camera_ip", ""))
            
            # 🟢 Restaurar dispositivos buscando texto parcial
            mic_name = cfg.get("mic_device_name", "")
            if mic_name:
                idx = self.cmb_mic.findText(mic_name, Qt.MatchFlag.MatchContains)
                if idx >= 0: self.cmb_mic.setCurrentIndex(idx)
                
            spk_name = cfg.get("speaker_device_name", "")
            if spk_name:
                idx = self.cmb_speaker.findText(spk_name, Qt.MatchFlag.MatchContains)
                if idx >= 0: self.cmb_speaker.setCurrentIndex(idx)
                
            cam_name = cfg.get("camera_device_name", "")
            if cam_name:
                idx = self.cmb_camera.findText(cam_name, Qt.MatchFlag.MatchContains)
                if idx >= 0: self.cmb_camera.setCurrentIndex(idx)
                
            # Restaurar volumen visual guardado
            sens = cfg.get("mic_sensitivity", 50)
            self.sld_mic_sens.setValue(sens)
            self.lbl_mic_sens_val.setText(f"{sens}%")

            spotify_id = cfg.get("spotify_client_id", "")
            spotify_secret = cfg.get("spotify_client_secret", "")
            self.inp_spotify_id.setText(spotify_id)
            self.inp_spotify_secret.setText(spotify_secret)
            
            has_custom = bool(spotify_id or spotify_secret)
            self.chk_advanced_spotify.setChecked(has_custom)
            self._toggle_advanced_spotify(has_custom)
            
            self.lbl_spotify_status.setText(self.check_spotify_auth_status())
            self._toggle_ollama_fields()
        except Exception as e:
            print(f"[Settings] Fallo al cargar configs locales: {e}")
            self._toggle_ollama_fields()
            self._toggle_advanced_spotify(False)

    def save(self):
        try:
            theme_val = self.cmb_theme.currentData()
            cfg = {
                "gemini_api_key": self.inp_gemini.text().strip(),
                "openrouter_api_key": self.inp_openrouter.text().strip(),
                "ai_provider": self.cmb_ai_provider.currentData(),
                "ollama_url": self.inp_ollama_url.text().strip(),
                "ollama_model": self.inp_ollama_model.text().strip(),
                "performance_quality": self.sld_performance.value(),
                "jarvis_voice": self.cmb_voice.currentData(),
                "jarvis_theme": theme_val,
                "gpu_acceleration": self.chk_gpu.isChecked(),
                "mic_sensitivity": self.sld_mic_sens.value(), 
                "camera_ip": self.inp_camera_ip.text().strip(),
                "user_name": self.inp_user_name.text().strip() or "Señor",
                "spotify_client_id": self.inp_spotify_id.text().strip(),
                "spotify_client_secret": self.inp_spotify_secret.text().strip(),
                "spotify_redirect_uri": self.inp_spotify_uri.text().strip(),
                
                # 🟢 Guardamos el Nombre exacto de los dispositivos, no el índice
                "mic_device_name": self.cmb_mic.currentText(),
                "speaker_device_name": self.cmb_speaker.currentText(),
                "camera_device_name": self.cmb_camera.currentText()
            }
            save_api_keys(cfg)
            
            if hasattr(self.parent(), "apply_new_theme"):
                self.parent().apply_new_theme(theme_val)
                
            JarvisMessageBox(self, "Success", "JARVIS Configurations saved, sir.").exec()
            self.accept()
        except Exception as e:
            JarvisMessageBox(self, "Error", f"Failed to save settings: {e}", is_error=True).exec()

    def check_spotify_auth_status(self):
        try:
            client_id = self.inp_spotify_id.text().strip() or "455d312ba37a4e0c8be373b53f6305a4"
            client_secret = self.inp_spotify_secret.text().strip() or "5a075d9e504c4f3cb4cc6c5e533d1b4a"
            redirect_uri = self.inp_spotify_uri.text().strip() or "http://127.0.0.1:8888/callback"
            
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            sp_oauth = SpotifyOAuth(client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri, open_browser=False)
            token = sp_oauth.get_cached_token()
            if token:
                self.lbl_spotify_status.setStyleSheet("color: #1DB954; font-weight: bold;")
                return "Conectado"
            else:
                self.lbl_spotify_status.setStyleSheet("color: #e11d48; font-weight: bold;")
                return "Desconectado"
        except Exception as e:
            self.lbl_spotify_status.setStyleSheet("color: #e11d48; font-style: italic;")
            return f"Error: {e}"

    def connect_spotify(self):
        client_id = self.inp_spotify_id.text().strip() or "455d312ba37a4e0c8be373b53f6305a4"
        client_secret = self.inp_spotify_secret.text().strip() or "5a075d9e504c4f3cb4cc6c5e533d1b4a"
        custom_redirect_uri = self.inp_spotify_uri.text().strip() or "http://127.0.0.1:8765/callback"
        
        try:
            parsed_uri = urllib.parse.urlparse(custom_redirect_uri)
            port = parsed_uri.port or 8765
        except Exception:
            port = 8765
            
        redirect_uri = f"http://127.0.0.1:{port}/callback"

        self.lbl_spotify_status.setText("Abriendo navegador...")
        self.lbl_spotify_status.setStyleSheet("color: #fbbf24; font-style: italic;")
        self.btn_spotify_login.setEnabled(False)

        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            sp_oauth = SpotifyOAuth(
                client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri,
                scope="user-modify-playback-state user-read-playback-state user-read-currently-playing user-library-read",
                open_browser=False, cache_path=str(Path(__file__).parent / ".spotify_cache")
            )
            auth_url = sp_oauth.get_authorize_url()
        except Exception as e:
            self.spotify_auth_failed(f"Error generando URL de auth: {e}")
            return

        auth_complete = threading.Event()
        auth_result = {"success": False, "error": ""}
        outer_self = self

        class _SpotifyCallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass 
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed.query)

                if parsed.path == "/callback":
                    code = qs.get("code", [None])[0]
                    error = qs.get("error", [None])[0]
                    if error:
                        auth_result["error"] = error
                        auth_complete.set()
                    elif code:
                        try:
                            sp_oauth.get_access_token(code, as_dict=False)
                            auth_result["success"] = True
                            success_html = "<html><body style='background:#060400; color:#1DB954; font-family:sans-serif; text-align:center; padding-top:50px;'><h2>Spotify Conectado a JARVIS</h2><p>Puedes cerrar esta pestaña.</p></body></html>".encode("utf-8")
                            self.send_response(200)
                            self.send_header("Content-Type", "text/html; charset=utf-8")
                            self.end_headers()
                            self.wfile.write(success_html)
                            auth_complete.set()
                        except Exception as ex:
                            auth_result["error"] = str(ex)
                            auth_complete.set()

        def _run_server():
            try:
                server = HTTPServer(("127.0.0.1", port), _SpotifyCallbackHandler)
                server.timeout = 1.0
                elapsed = 0
                while not auth_complete.is_set() and elapsed < 300:
                    server.handle_request()
                    elapsed += 1
                server.server_close()

                if auth_result["success"]:
                    QTimer.singleShot(0, outer_self.spotify_auth_success)
                else:
                    err = auth_result.get("error", "Tiempo agotado o cancelado")
                    QTimer.singleShot(0, lambda: outer_self.spotify_auth_failed(err))
            except Exception as ex:
                QTimer.singleShot(0, lambda: outer_self.spotify_auth_failed(str(ex)))

        threading.Thread(target=_run_server, daemon=True).start()
        threading.Thread(target=lambda: (__import__('time').sleep(0.5), webbrowser.open(auth_url)), daemon=True).start()

    def spotify_auth_success(self):
        self.btn_spotify_login.setEnabled(True)
        self.lbl_spotify_status.setText("Conectado")
        self.lbl_spotify_status.setStyleSheet("color: #1DB954; font-weight: bold;")
        JarvisMessageBox(self, "Spotify API", "¡Autenticación con Spotify exitosa, sir!").exec()

    def spotify_auth_failed(self, error):
        self.btn_spotify_login.setEnabled(True)
        self.lbl_spotify_status.setText("Error")
        self.lbl_spotify_status.setStyleSheet("color: #e11d48; font-weight: bold;")
        JarvisMessageBox(self, "Spotify API Error", f"Fallo al conectar: {error}", is_error=True).exec()

    def update_style(self):
        self.setStyleSheet(f"""
            QDialog {{ background-color: {C_BG}; border: 2px solid {C_PRI}; }}
            QLabel {{ color: {C_TEXT}; font-weight: bold; }}
            QLineEdit, QComboBox {{ background: rgba(0,0,0,0.4); border: 1px solid {C_BORDER}; color: white; padding: 5px; border-radius: 4px; }}
            QComboBox QAbstractItemView {{ background-color: {C_BG}; color: white; selection-background-color: {C_PRI}; selection-color: {C_BG}; }}
            QCheckBox {{ color: {C_PRI}; font-weight: bold; }}
            QPushButton {{ background-color: rgba(10, 22, 32, 0.7); color: {C_PRI}; border: 1.5px solid {C_PRI}; font-weight: bold; padding: 6px 15px; border-radius: 4px; }}
            QPushButton:hover {{ background-color: {C_PRI}; color: {C_BG}; }}
        """)