import warnings
warnings.filterwarnings("ignore")

import asyncio
import json
import re
import sys
import threading
import time
import os
import collections
import importlib
import datetime
import traceback
import unicodedata
import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
from google import genai
from google.genai import types
from PyQt6.QtWidgets import QApplication
from dotenv import load_dotenv
import websockets

from ui import JarvisUI
from config_manager import load_api_keys
import audio_devices
from actions import neural_learner
from actions import voice_guard

SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHANNELS = 1
MODEL = "gemini-3.1-flash-live-preview"
TOOL_DECLARATIONS = []
FUNCIONES_DISPONIBLES = {}
TOOL_TIMEOUTS = {}          # nombre → segundos; una acción puede declarar TOOL_TIMEOUT
TIMEOUT_HERRAMIENTA = 30.0  # límite por defecto para las que no declaran nada
TOOL_EN_FONDO = set()       # acciones con TOOL_BACKGROUND: se ejecutan en segundo plano
                            # y el resultado se anuncia por voz cuando terminan de verdad
CATALOG_VERSION = 0         # sube en cada auto_descubrir: run() detecta catálogos obsoletos

_LOG_FILE = None

def log_guardia(mensaje):
    global _LOG_FILE
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    linea = f"[{ts}] {mensaje}"
    try:
        print(linea)
    except Exception:
        # Consolas sin UTF-8 no deben tumbar al asistente por un emoji
        try: print(linea.encode("ascii", "replace").decode("ascii"))
        except Exception: pass
    try:
        # Handle persistente con búfer de línea: abrir/cerrar el archivo por cada
        # línea hacía que OneDrive resincronizara el log en cada evento (el
        # proyecto vive en una carpeta sincronizada). Abierto se sube una sola
        # vez, al cerrar la aplicación.
        if _LOG_FILE is None:
            _LOG_FILE = open("guardia_log.txt", "a", encoding="utf-8", buffering=1)
        _LOG_FILE.write(linea + "\n")
    except Exception:
        pass

def _parece_pregunta(texto: str) -> bool:
    """¿La frase de I.R.I.S espera una respuesta del usuario?

    Los signos '¿?' son la señal principal, pero la transcripción oficial del AUDIO
    la genera el transcriptor de Google y a veces llega sin puntuación: una pregunta
    hablada quedaba clasificada como afirmación y el micrófono se cerraba en la cara
    del usuario. Esta red de seguridad reconoce la ESTRUCTURA interrogativa del
    español en la última frase, sin depender de los signos.
    """
    if "?" in texto or "¿" in texto:
        return True
    t = "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                if unicodedata.category(c) != "Mn")
    frases = [f.strip() for f in re.split(r"[.!\n;]+", t) if f.strip()]
    if not frases:
        return False
    ultima = frases[-1]
    palabras = ultima.split()
    if not palabras:
        return False

    interrogativas = {"que", "cual", "cuales", "como", "donde", "adonde", "cuando",
                      "cuanto", "cuanta", "cuantos", "cuantas", "quien", "quienes"}
    # "que descanses", "que tengas buena noche": deseos de despedida, no preguntas
    deseos = ("descans", "duerm", "disfrut", "aproveche", "te vaya", "le vaya",
              "tengas", "tenga", "buen dia", "buena noche", "buenas noches", "suerte")
    # "¿qué canción...?", "¿cuál prefieres...?" (sin los signos)
    if palabras[0] in interrogativas:
        if palabras[0] == "que" and any(d in ultima for d in deseos):
            pass  # desiderativo ("que descanses señor"), sigue evaluando otras señales
        else:
            return True
    # "¿en qué puedo ayudarte?", "¿de cuál hablas?"
    if len(palabras) > 1 and palabras[0] in {"en", "a", "de", "por", "para", "con",
                                             "sobre", "desde", "hasta"} \
            and palabras[1] in interrogativas:
        return True
    # "¿quieres que lo abra?", "¿procedo?", "¿hay algo más?"
    if palabras[0] in {"quieres", "deseas", "necesitas", "prefieres", "puedo",
                       "procedo", "confirmas", "hay", "tienes", "seguro", "segura"}:
        return True
    # Ofertas y peticiones de respuesta en cualquier punto de la última frase
    patrones = ("quieres", "deseas", "necesitas", "prefieres", "te gustaria",
                "te parece", "te apetece", "te interesa", "puedo ayudarte",
                "en que puedo", "algo mas", "alguna otra", "me confirmas",
                "confirmame", "dime", "cuentame", "indicame", "avisame",
                "hazme saber", "me dices")
    if any(p in ultima for p in patrones):
        return True
    # Coletillas de confirmación al final: "...verdad", "...cierto"
    return ultima.endswith(("verdad", "cierto", "no es asi", "de acuerdo"))


def auto_descubrir_herramientas():
    log_guardia("⚙️ Descubriendo herramientas en /actions...")
    global TOOL_DECLARATIONS, FUNCIONES_DISPONIBLES, CATALOG_VERSION

    # El reload reinicia el estado en memoria de los módulos. Casi todo se recarga
    # de disco solo (huella de voz, pesos de la red), pero un enrolamiento PENDIENTE
    # ("aprende mi voz" aún sin grabar) se perdería en silencio: se preserva a mano.
    enroll_pendiente = False
    try:
        enroll_pendiente = importlib.import_module("actions.voice_guard").enroll_pendiente()
    except Exception:
        pass

    if not os.path.exists("actions"):
        os.makedirs("actions")
        return

    # 🚀 Se construye el catálogo NUEVO en variables locales y se intercambia al
    # final: esta función ahora puede correr en un hilo (asyncio.to_thread) sin
    # que run() o el ejecutor de herramientas vean un catálogo a medio llenar.
    decl_nuevas, funcs_nuevas, fondo_nuevo, timeouts_nuevos = [], {}, set(), {}

    for archivo in os.listdir("actions"):
        if archivo.endswith(".py") and archivo != "__init__.py":
            nombre = archivo[:-3]
            try:
                modulo = importlib.import_module(f"actions.{nombre}")
                importlib.reload(modulo)

                if hasattr(modulo, nombre):
                    funcs_nuevas[nombre] = getattr(modulo, nombre)
                if hasattr(modulo, "TOOL_DEF"):
                    decl_nuevas.append(modulo.TOOL_DEF)
                # ⏱️ Las herramientas lentas (auto_programmer, self_edit llaman a una
                # IA externa que tarda minutos) declaran su propio límite de tiempo.
                if hasattr(modulo, "TOOL_TIMEOUT"):
                    try:
                        timeouts_nuevos[nombre] = float(modulo.TOOL_TIMEOUT)
                    except Exception:
                        pass
                if getattr(modulo, "TOOL_BACKGROUND", False):
                    fondo_nuevo.add(nombre)
            except Exception as e:
                log_guardia(f"⚠️ Error al auto-descubrir '{nombre}':\n{traceback.format_exc()}")

    TOOL_DECLARATIONS[:] = decl_nuevas
    FUNCIONES_DISPONIBLES.clear(); FUNCIONES_DISPONIBLES.update(funcs_nuevas)
    TOOL_EN_FONDO.clear(); TOOL_EN_FONDO.update(fondo_nuevo)
    TOOL_TIMEOUTS.clear(); TOOL_TIMEOUTS.update(timeouts_nuevos)
                
    if enroll_pendiente:
        try:
            importlib.import_module("actions.voice_guard").solicitar_enrolamiento()
        except Exception:
            pass

    CATALOG_VERSION += 1
    log_guardia(f"⚙️ Herramientas cargadas (catálogo v{CATALOG_VERSION}): {list(FUNCIONES_DISPONIBLES.keys())}")

class IRISCore:
    def __init__(self, ui):
        log_guardia("🧠 [INIT] Inicializando clase IRISCore (Máquina de Estados Perfecta)...")
        self.ui = ui
        self.cfg = load_api_keys()
        api_key = os.getenv("GEMINI_API_KEY") or self.cfg.get("gemini_api_key", "")
        self.client = genai.Client(api_key=api_key)

        # 🟢 MÁQUINA DE ESTADOS ("SUSPENSION", "ESCUCHANDO", "HABLANDO",
        #    "VENTANA" = seguimiento sin wake-word, "ENROLANDO" = grabando tu huella de voz)
        self.estado = "SUSPENSION"
        self.texto_turno = ""          # Texto que llega en las parts del modelo
        self.texto_transcripcion = ""  # Transcripción oficial del audio que habla I.R.I.S.
        self.texto_usuario = ""        # Transcripción de lo que dijo el usuario (para aprender)
        self.loop = None
        self.vosk_lock = threading.Lock()

        # 🗝️ Guardián de voz / ventana de seguimiento
        self.ventana_hasta = 0.0       # momento en que expira la ventana sin wake-word
        self._ruido = None             # piso de ruido para el detector de actividad de voz
        self._rechazos_seguidos = 0    # wake-words seguidos rechazados por la biometría
        self._turno_completo = False   # el servidor confirmó fin de turno (transcripción entera)
        self._resumption_handle = None # asa para reanudar la sesión Live si la conexión se cae
        self._ultima_llamada = None    # firma (herramienta, args) de la última ejecución real
        self._omitir_repeticion = False  # tras reanudar sesión: ignorar la llamada calcada
        self.session_actual = None     # sesión Live viva (para inyectar avisos de tareas)
        self.avisos_queue = asyncio.Queue()      # resultados de tareas en segundo plano
        self._renovar_sesion = asyncio.Event()   # pide reconectar para recargar herramientas
        self._tareas_fondo_activas = 0           # tareas de fondo aún trabajando
        self._tareas_fondo = set()               # referencias vivas (asyncio solo guarda débiles)
        self._vosk_con_senal = False             # Vosk descansa durante silencio digital

        # 🔁 Si venimos de un reinicio del núcleo, retomamos la MISMA conversación:
        # _reiniciar_tras_hablar dejó el asa de reanudación guardada en disco.
        try:
            ruta_reanudar = os.path.join("config", "session_reanudar.json")
            if os.path.exists(ruta_reanudar):
                with open(ruta_reanudar, "r", encoding="utf-8") as f:
                    datos_reanudar = json.load(f)
                os.remove(ruta_reanudar)
                if datos_reanudar.get("handle") and time.time() - float(datos_reanudar.get("ts", 0)) < 180:
                    self._resumption_handle = datos_reanudar["handle"]
                    log_guardia("🔁 Reinicio del núcleo detectado: retomaré la conversación donde estaba.")
        except Exception as e:
            log_guardia(f"⚠️ No pude leer el asa de reanudación tras el reinicio: {e}")

        # 🎚️ "Sensibilidad del micrófono" de Ajustes: hasta ahora se guardaba en el
        # config y NADIE la leía. Es el suelo mínimo del detector de voz, así que un
        # micrófono flojo (como una entrada de línea) ya se puede compensar sin tocar código.
        try:
            sens = float(self.cfg.get("mic_sensitivity", 50))
        except Exception:
            sens = 50.0
        self._vad_min = max(60.0, 500.0 - 4.0 * float(np.clip(sens, 0.0, 100.0)))
        self._habla_acum = b""         # ráfaga de voz acumulada pendiente de verificar
        self._bloques_voz = 0
        self._sil_seguidos = 0
        self._enroll_datos = []        # audio crudo mientras se graba tu huella
        self._enroll_ini = 0.0

        self.mic_idx = None
        self.spk_idx = None
        self.mic_nombre = "desconocido"
        self._nivel_pico = 0.0        # pico de señal del micrófono entre revisiones
        self._silencio_avisado = False

        try:
            # 🟢 La elección vive en audio_devices.py, compartida con guardia.py:
            # Ajustes manda, y si no hay nada configurado se prefiere un micrófono
            # FÍSICO (nunca un virtual mudo ni la línea de audio del juego).
            log_guardia(f"⚙️ Micrófonos disponibles: {audio_devices.describir_entradas()}")

            self.mic_idx, mic_nombre, aviso_mic = audio_devices.elegir_microfono(self.cfg.get("mic_device_name", ""))
            self.spk_idx, spk_nombre, aviso_spk = audio_devices.elegir_bocina(self.cfg.get("speaker_device_name", ""))
            self.mic_nombre = mic_nombre or "desconocido"

            if self.mic_idx is not None: log_guardia(f"⚙️ MICRÓFONO ASIGNADO: [{self.mic_idx}] {mic_nombre}")
            if aviso_mic: log_guardia(f"⚠️ {aviso_mic}")
            if self.spk_idx is not None: log_guardia(f"⚙️ BOCINA ASIGNADA: [{self.spk_idx}] {spk_nombre}")
            if aviso_spk: log_guardia(f"⚠️ {aviso_spk}")
        except Exception as e:
            log_guardia(f"⚠️ Fallo hardware. Error: {e}")

        log_guardia("🧠 [INIT] Cargando Vosk...")
        SetLogLevel(-1)
        try:
            self.vosk_model = Model("vosk_model")
            self.recognizer = KaldiRecognizer(self.vosk_model, SEND_SAMPLE_RATE)
            self.WAKE_WORDS = {"iris", "yris", "iriz", "yriz", "jarvis"}
        except Exception as e:
            log_guardia(f"❌ Error crítico Vosk: {e}")
        
        self.audio_buffer = collections.deque(maxlen=15)
        self.audio_in_queue = asyncio.Queue()
        self.out_queue = asyncio.Queue()
        log_guardia("🧠 [INIT] Sistema listo.")

    def actualizar_ui(self):
        if not self.loop: return
        if self.estado == "SUSPENSION":
            self.loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ SUSPENSIÓN")
            self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Micrófono desactivado, vuelve a decir Iris para llamar su atención")
        elif self.estado == "ESCUCHANDO":
            self.loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🌐 ESCUCHANDO")
            self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Micrófono abierto. Esperando tu respuesta...")
        elif self.estado == "HABLANDO":
            self.loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🗣️ HABLANDO...")
        elif self.estado == "VENTANA":
            self.loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🕓 VENTANA DE VOZ")
            self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Puedes seguir hablando sin decir Iris (solo tu voz me reactiva)...")
        elif self.estado == "ENROLANDO":
            self.loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🎙️ GRABANDO VOZ")
            self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Grabando tu huella de voz. Habla con naturalidad unos 30 segundos...")

    def _reset_recognizer_seguro(self):
        if hasattr(self, 'recognizer'):
            with self.vosk_lock:
                self.recognizer.Reset()

    def _abrir_microfono(self, motivo=""):
        """Pasa a ESCUCHANDO y manda a Gemini el audio retenido en el buffer
        (así no se pierde el inicio de la frase que provocó la apertura)."""
        self._reset_recognizer_seguro()
        self.estado = "ESCUCHANDO"
        self._habla_acum = b""
        self._bloques_voz = 0
        self._sil_seguidos = 0
        log_guardia(f"✨ Micrófono abierto ({motivo}).")
        try:
            import winsound
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except: pass

        self.actualizar_ui()

        if self.loop:
            for chunk in self.audio_buffer:
                self.loop.call_soon_threadsafe(self.out_queue.put_nowait, chunk)
        self.audio_buffer.clear()

    def _iniciar_enrolamiento(self):
        """Arranca la grabación de la huella de voz (30 segundos de captura)."""
        self.estado = "ENROLANDO"
        self._enroll_datos = []
        self._enroll_ini = time.monotonic()
        self._reset_recognizer_seguro()
        log_guardia("🎙️ ENROLAMIENTO INICIADO: grabando la voz del usuario 30s...")
        try:
            import winsound
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except: pass

    # 🟢 EVALUADOR DEFINITIVO DE FRASES
    def evaluar_texto_y_estado(self, tras_audio=False):
        # Usamos el texto de las parts; si el modelo habló solo con audio,
        # usamos la transcripción oficial de su voz.
        texto = (self.texto_turno.strip() or self.texto_transcripcion.strip())

        # 🎙️ PRIORIDAD ABSOLUTA: si hay un enrolamiento pendiente, arranca en cuanto
        # I.R.I.S termina su turno (aunque su frase haya acabado en pregunta o sin texto).
        if voice_guard.enroll_pendiente() and (tras_audio or texto):
            voice_guard.consumir_enroll()
            self.texto_turno = ""
            self.texto_transcripcion = ""
            self.texto_usuario = ""
            self._iniciar_enrolamiento()
            self.actualizar_ui()
            return

        if not texto:
            # Turno vacío. Si venimos de reproducir audio (o quedamos en HABLANDO),
            # NUNCA nos quedamos atascados. Pero cerrar en seco era injusto: si la
            # transcripción se perdió (p. ej. la conexión se recicló mientras el
            # audio aún sonaba), I.R.I.S pudo haber hecho una pregunta que nunca
            # veremos. Con el guardián activo dejamos la ventana biométrica: solo
            # TU voz reabre, y el silencio la cierra sola.
            if tras_audio or self.estado == "HABLANDO":
                if voice_guard.lock_activo() and voice_guard.ventana_segundos() > 0:
                    log_guardia("🕓 Turno de voz sin transcripción: abro ventana de seguimiento "
                                "por si fue una pregunta (solo tu voz reabre).")
                    self.estado = "VENTANA"
                    self.ventana_hasta = time.monotonic() + voice_guard.ventana_segundos()
                    self._habla_acum = b""
                    self._bloques_voz = 0
                    self._sil_seguidos = 0
                    self._reset_recognizer_seguro()
                    self.audio_buffer.clear()
                else:
                    log_guardia("🔇 Turno de voz sin transcripción. Cerrando micrófono por seguridad.")
                    self.estado = "SUSPENSION"
                    self._reset_recognizer_seguro()
                self.texto_usuario = ""
                self.actualizar_ui()
            return

        log_guardia(f"🔎 Analizando respuesta física de I.R.I.S: '{texto}'")

        if "?" in texto or "¿" in texto:
            log_guardia("❓ PREGUNTA DETECTADA (signos). Manteniendo micrófono abierto.")
            self.estado = "ESCUCHANDO"
        elif _parece_pregunta(texto):
            log_guardia("❓ PREGUNTA DETECTADA (estructura interrogativa, la transcripción "
                        "vino sin signos). Manteniendo micrófono abierto.")
            self.estado = "ESCUCHANDO"
        elif voice_guard.lock_activo() and voice_guard.ventana_segundos() > 0:
            # 🕓 VENTANA DE SEGUIMIENTO: unos segundos para seguir hablando sin
            # wake-word, custodiados por la huella de voz (solo TU voz reabre).
            log_guardia(f"🕓 AFIRMACIÓN. Abriendo ventana de seguimiento de {voice_guard.ventana_segundos():.0f}s (solo tu voz).")
            self.estado = "VENTANA"
            self.ventana_hasta = time.monotonic() + voice_guard.ventana_segundos()
            self._habla_acum = b""
            self._bloques_voz = 0
            self._sil_seguidos = 0
            self._reset_recognizer_seguro()
            self.audio_buffer.clear()
        else:
            log_guardia("🔇 AFIRMACIÓN DETECTADA. Cerrando micrófono por completo.")
            self.estado = "SUSPENSION"
            self._reset_recognizer_seguro()

        # Limpiamos para la próxima vez
        self.texto_turno = ""
        self.texto_transcripcion = ""
        self.texto_usuario = ""
        self.actualizar_ui()

    async def _listen_audio(self):
        log_guardia("🎤 Escucha iniciada.")

        def callback(indata, frames, time_info, status):
            if status: pass
            try:
                def safe_update_audio():
                    try:
                        if hasattr(self.ui, '_win') and getattr(self.ui._win, 'orb', None):
                            self.ui._win.orb.set_audio(nivel)
                    except RuntimeError: pass
                        
                # Una sola conversión por bloque (antes había dos astype distintos)
                arr = indata.astype(np.float64)
                vol_max = float(np.max(np.abs(arr)))
                nivel = vol_max / 32768.0
                if nivel > self._nivel_pico: self._nivel_pico = nivel

                if self.loop: self.loop.call_soon_threadsafe(safe_update_audio)
                
                data_bytes = bytes(indata)
                
                # REGLAS DE LA MÁQUINA DE ESTADOS
                if self.estado == "HABLANDO":
                    # I.R.I.S habla = No te escucha
                    if self.loop: self.loop.call_soon_threadsafe(self.out_queue.put_nowait, b'\x00' * len(data_bytes))

                elif self.estado == "ENROLANDO":
                    # 🎙️ Grabando tu huella de voz (a Gemini le mandamos silencio)
                    if self.loop: self.loop.call_soon_threadsafe(self.out_queue.put_nowait, b'\x00' * len(data_bytes))
                    self._enroll_datos.append(data_bytes)

                    if len(self._enroll_datos) % 20 == 0:  # cada ~5 segundos
                        trans = int(time.monotonic() - self._enroll_ini)
                        if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, f"🎙️ Grabando tu voz... {trans}s / 30s")

                    if time.monotonic() - self._enroll_ini >= 30.0:
                        datos = b"".join(self._enroll_datos)
                        self._enroll_datos = []
                        # Limpiamos texto acumulado durante la grabación para no
                        # evaluar frases viejas al volver a la guardia normal
                        self.texto_turno = ""
                        self.texto_transcripcion = ""
                        self.texto_usuario = ""
                        self.estado = "SUSPENSION"
                        self.actualizar_ui()

                        def procesar_huella(audio=datos):
                            try:
                                ok, msg = voice_guard.crear_perfil(audio)
                            except Exception as e:
                                ok, msg = False, f"Error creando la huella de voz: {e}"
                            icono = "✅" if ok else "❌"
                            log_guardia(f"{icono} {msg}")
                            if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, f"{icono} {msg}")
                            try:
                                import winsound
                                winsound.PlaySound("SystemAsterisk" if ok else "SystemHand", winsound.SND_ALIAS | winsound.SND_ASYNC)
                            except: pass
                        threading.Thread(target=procesar_huella, daemon=True).start()

                elif self.estado in ("SUSPENSION", "VENTANA"):
                    # Mandamos ceros a Google para mantener ping, Vosk analiza audio real
                    if self.loop: self.loop.call_soon_threadsafe(self.out_queue.put_nowait, b'\x00' * len(data_bytes))

                    self.audio_buffer.append(data_bytes)

                    # Detector de actividad de voz (piso de ruido adaptativo).
                    # El primer bloque de un stream recién abierto suele traer un golpe
                    # fuerte; arrancar el piso de ruido con él lo envenenaba (medido: se
                    # inicializaba en 1535, dejando el umbral en 5373, y NINGÚN bloque de
                    # voz lo superaba en 10s). Por eso el arranque está acotado y el piso
                    # nunca se queda por encima de lo que realmente entra.
                    rms = float(np.sqrt(np.mean(arr ** 2)))
                    if self._ruido is None: self._ruido = float(np.clip(rms, 1.0, 150.0))
                    voz_activa = rms > max(self._ruido * 3.5, self._vad_min)
                    if not voz_activa:
                        self._ruido = 0.95 * self._ruido + 0.05 * max(rms, 1.0)
                    elif rms < self._ruido:
                        self._ruido = max(rms, 1.0)

                    # 🚀 Silencio digital absoluto: Vosk no gasta CPU en ceros. Se le
                    # entrega un último bloque de ceros para que cierre lo pendiente
                    # y después descansa hasta que vuelva a haber señal.
                    if vol_max == 0.0 and not self._vosk_con_senal:
                        texto = ""
                    else:
                        self._vosk_con_senal = vol_max > 0.0
                        with self.vosk_lock:
                            if self.recognizer.AcceptWaveform(data_bytes):
                                res = json.loads(self.recognizer.Result())
                                texto = res.get("text", "").lower()
                            else:
                                res = json.loads(self.recognizer.PartialResult())
                                texto = res.get("partial", "").lower()

                    palabras_detectadas = set(texto.replace(",", "").replace(".", "").split())

                    if self.WAKE_WORDS.intersection(palabras_detectadas):
                        if voice_guard.lock_activo():
                            # 🗝️ Solo TU voz puede despertar a I.R.I.S.
                            # Tomamos ~2.5s (10 bloques): con 1.5s quedaba medio segundo de
                            # voz y el embedding salía inestable, hundiendo la similitud.
                            recorte = b"".join(list(self.audio_buffer)[-10:])
                            ok, sim, seg = voice_guard.verificar_bytes(recorte)
                            if ok is False or (ok is None and voice_guard.modo_estricto()):
                                self._rechazos_seguidos += 1
                                log_guardia(f"🔒 Wake-word con voz NO reconocida (similitud {sim:.2f}, "
                                            f"voz {seg:.1f}s, rechazo {self._rechazos_seguidos}/3). Ignorado.")
                                # 🛟 RED DE SEGURIDAD: una huella mal calibrada no puede dejar
                                # al usuario encerrado fuera de su propio asistente. Tras tres
                                # rechazos seguidos abrimos igual y explicamos por qué.
                                if self._rechazos_seguidos >= 3:
                                    self._rechazos_seguidos = 0
                                    aviso = (f"Te he rechazado 3 veces por biometría (última similitud {sim:.2f}, "
                                             "umbral demasiado alto). Abro el micrófono igualmente: pídeme "
                                             "'aprende mi voz' para regrabar tu huella.")
                                    log_guardia(f"🛟 {aviso}")
                                    if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, f"⚠️ {aviso}")
                                    self._abrir_microfono("wake-word (guardián omitido tras 3 rechazos)")
                                else:
                                    with self.vosk_lock:
                                        self.recognizer.Reset()
                            else:
                                self._rechazos_seguidos = 0
                                detalle = f"voz verificada, similitud {sim:.2f}" if ok else "evidencia corta, modo flexible"
                                self._abrir_microfono(f"wake-word ({detalle})")
                        else:
                            self._abrir_microfono("wake-word")

                    # 🕓 Lógica extra de la VENTANA DE SEGUIMIENTO
                    if self.estado == "VENTANA":
                        if time.monotonic() > self.ventana_hasta:
                            log_guardia("🕓 Ventana de seguimiento cerrada por silencio. Volviendo a guardia.")
                            self.estado = "SUSPENSION"
                            self._habla_acum = b""; self._bloques_voz = 0; self._sil_seguidos = 0
                            self.actualizar_ui()
                        else:
                            if voz_activa:
                                self._habla_acum += data_bytes
                                self._bloques_voz += 1
                                self._sil_seguidos = 0
                            elif self._bloques_voz > 0:
                                self._sil_seguidos += 1

                            # ¿Hay suficiente voz junta para identificar al hablante?
                            listo = (self._bloques_voz >= 6) or (self._sil_seguidos >= 1 and self._bloques_voz >= 3)
                            if listo:
                                ok, sim, seg = voice_guard.verificar_bytes(self._habla_acum)
                                self._habla_acum = b""; self._bloques_voz = 0; self._sil_seguidos = 0
                                if ok is True:
                                    log_guardia(f"🗝️ Tu voz reconocida (similitud {sim:.2f}). Continuamos sin wake-word.")
                                    self._abrir_microfono("continuación por tu voz")
                                elif ok is False:
                                    log_guardia(f"🔇 Voz ajena ignorada en la ventana (similitud {sim:.2f}).")
                            elif self._sil_seguidos >= 2 and 0 < self._bloques_voz < 3:
                                # Ráfaga demasiado corta (un golpe, una tos): descartada
                                self._habla_acum = b""; self._bloques_voz = 0; self._sil_seguidos = 0

                elif self.estado == "ESCUCHANDO":
                    # Mandamos tu voz real a Google
                    if self.loop: self.loop.call_soon_threadsafe(self.out_queue.put_nowait, data_bytes)

            except Exception as e: pass

        # 🟢 Apertura a prueba de fallos: si el segundo intento también reventaba,
        # la excepción se comía la tarea entera y I.R.I.S. se quedaba sorda SIN
        # decir nada (la UI seguía viéndose perfecta). Ahora siempre lo avisamos.
        stream = None
        intentos = [("micrófono asignado", {"device": self.mic_idx}), ("micrófono por defecto", {})]
        for descripcion, extra in intentos:
            try:
                stream = sd.InputStream(samplerate=SEND_SAMPLE_RATE, channels=CHANNELS, dtype="int16",
                                        blocksize=4000, callback=callback, **extra)
                break
            except Exception as e:
                log_guardia(f"⚠️ No pude abrir el {descripcion}: {e}")

        if stream is None:
            aviso = ("SIN MICRÓFONO: no pude abrir ninguna entrada de audio, así que no puedo oírte. "
                     "Cierra las apps que estén usando el micrófono (Voicemod, Discord, OBS) y reinícieme.")
            log_guardia(f"❌ {aviso}")
            if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, f"⚠️ {aviso}")
            while True: await asyncio.sleep(1)

        with stream:
            while True: await asyncio.sleep(1)

    async def _vigilar_microfono(self):
        """🔇 Detector de sordera. Un micrófono virtual apagado (Voicemod, Steam,
        NVIDIA Broadcast) se abre sin error pero entrega silencio digital: parecería
        que I.R.I.S. te ignora. En vez de callar, lo decimos con nombre y apellido."""
        await asyncio.sleep(8)
        segundos_mudo = 0
        while True:
            await asyncio.sleep(4)
            pico, self._nivel_pico = self._nivel_pico, 0.0

            if self.estado in ("HABLANDO", "ENROLANDO"):
                continue

            if pico < 0.0015:
                segundos_mudo += 4
            else:
                segundos_mudo = 0
                self._silencio_avisado = False

            if segundos_mudo >= 20 and not self._silencio_avisado:
                self._silencio_avisado = True
                aviso = (f"El micrófono '{self.mic_nombre}' no está entregando señal alguna. "
                         "Si es un micrófono virtual (Voicemod, Steam, NVIDIA Broadcast), abre su app o "
                         "elige tu micrófono físico en Ajustes; si no, revisa que no esté silenciado.")
                log_guardia(f"🔇 {aviso}")
                if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, f"⚠️ {aviso}")

    async def _send_realtime(self, session):
        try:
            while True:
                chunk = await self.out_queue.get()
                data = bytearray(chunk)
                while not self.out_queue.empty():
                    try: data.extend(self.out_queue.get_nowait())
                    except asyncio.QueueEmpty: break
                
                await session.send_realtime_input(audio=types.Blob(data=bytes(data), mime_type="audio/pcm;rate=16000"))
                await asyncio.sleep(0.01)
        except websockets.exceptions.ConnectionClosedError as e:
            log_guardia(f"🔌 Conexión con Gemini cerrada (envío): code={getattr(e, 'code', '?')} reason={getattr(e, 'reason', '')!r} {e}")
            return
        except asyncio.TimeoutError:
            log_guardia("🔌 Timeout enviando audio a Gemini.")
            return
        except Exception:
            log_guardia(f"❌ Error enviando audio a Gemini (la sesión se reiniciará):\n{traceback.format_exc()}")
            return

    async def _receive_audio(self, session):
        try:
          # 🔁 session.receive() entrega los mensajes de UN turno y su iterador
          # termina en cada fin de turno: eso NO es una desconexión (lo dice el
          # propio SDK: "responses will represent a complete model turn"). Antes
          # lo tratábamos como muerte de la sesión: cada respuesta reconectaba, y
          # al reanudar el modelo veía su última herramienta como pendiente y la
          # repetía (así se abrió AC/DC cuatro veces con cada "no, es todo").
          while True:
            async for response in session.receive():
                sc = response.server_content

                # 🔁 Asa de reanudación: si la conexión se cae, la siguiente se
                # reconecta CON el contexto de esta (el modelo recuerda el turno).
                sru = getattr(response, 'session_resumption_update', None)
                if sru is not None and getattr(sru, 'resumable', False) and getattr(sru, 'new_handle', None):
                    self._resumption_handle = sru.new_handle

                ga = getattr(response, 'go_away', None)
                if ga is not None:
                    # El servidor limita la duración de cada sesión. Si ignoramos el
                    # aviso nos corta con error 1008; mejor cerrar nosotros y volver
                    # a entrar con el asa de reanudación (la conversación continúa).
                    log_guardia(f"🔄 El servidor pide renovar la sesión (go_away, tiempo restante: "
                                f"{getattr(ga, 'time_left', '?')}). Reconectando con el contexto intacto.")
                    return

                if sc:
                    # 🧠 Transcripción de TU voz (materia prima del aprendizaje neuronal)
                    it = getattr(sc, 'input_transcription', None)
                    if it and it.text:
                        self.texto_usuario += it.text
                        # 💬 Tu transcripción en vivo, para las burbujas del diálogo
                        try:
                            t = self.texto_usuario.strip()
                            if t and hasattr(self.ui.puente, 'senal_usuario'):
                                self.ui.puente.senal_usuario.emit(t if len(t) < 90 else "..." + t[-85:])
                        except Exception: pass
                        # 🎙️ Red de seguridad: si pides grabar tu voz, lo agendamos
                        # nosotros mismos aunque el modelo olvide llamar la herramienta.
                        if not voice_guard.enroll_pendiente() and voice_guard.frase_pide_enrolamiento(self.texto_usuario):
                            voice_guard.solicitar_enrolamiento()
                            log_guardia("🎙️ Orden de enrolamiento detectada en tu voz. Se grabará al terminar el turno.")

                    # 🗣️ Transcripción de la voz de I.R.I.S (para evaluar ¿pregunta o afirmación?
                    # incluso cuando el modelo no envía texto en las parts)
                    ot = getattr(sc, 'output_transcription', None)
                    if ot and ot.text:
                        self._turno_completo = False
                        self.texto_transcripcion += ot.text
                        if not self.texto_turno:
                            t = self.texto_transcripcion
                            texto_mostrar = t if len(t) < 70 else "..." + t[-65:]
                            if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_transcripcion.emit, f"IRIS: {texto_mostrar}")

                if sc and sc.model_turn:
                    self._turno_completo = False
                    for part in sc.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            self.audio_in_queue.put_nowait(part.inline_data.data)

                        if part.text:
                            # ACUMULAMOS TODO EL TEXTO
                            self.texto_turno += part.text

                            texto_mostrar = self.texto_turno if len(self.texto_turno) < 70 else "..." + self.texto_turno[-65:]
                            if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_transcripcion.emit, f"IRIS: {texto_mostrar}")

                elif getattr(response, 'data', None):
                    self._turno_completo = False
                    self.audio_in_queue.put_nowait(response.data)

                if response.tool_call:
                    async def ejecutar_herramientas(llamadas):
                        try:
                            # 🔁 Anti-eco: tras reanudar una sesión caída, el modelo puede
                            # repetir su última llamada como si siguiera pendiente. Solo la
                            # primera tanda tras la reanudación se coteja contra la anterior.
                            cotejar_repeticion = self._omitir_repeticion
                            self._omitir_repeticion = False

                            respuestas_herramientas = []
                            for fc in llamadas:
                                name = fc.name
                                args = dict(fc.args) if fc.args else {}

                                firma = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
                                if cotejar_repeticion and firma == self._ultima_llamada:
                                    log_guardia(f"🔁 {name} repetida por el modelo tras reanudar la sesión: IGNORADA (ya se ejecutó).")
                                    kwargs_fr = {"name": name, "response": {"result": (
                                        "Esa acción YA se ejecutó correctamente hace un momento, antes de una "
                                        "reconexión. NO la repitas ni la menciones como nueva: continúa la conversación.")}}
                                    if getattr(fc, "id", None): kwargs_fr["id"] = fc.id
                                    respuestas_herramientas.append(types.FunctionResponse(**kwargs_fr))
                                    continue
                                self._ultima_llamada = firma

                                log_guardia(f"⚙️ Ejecutando herramienta: {name}")
                                if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, f"⚙️ Ejecutando: {name}...")

                                # 🧠 APRENDIZAJE: la frase del usuario + la herramienta usada
                                # se convierten en un ejemplo de entrenamiento de la red neuronal.
                                frase_usuario = self.texto_usuario.strip()
                                if frase_usuario and name in FUNCIONES_DISPONIBLES and name != "neural_learner":
                                    def entrenar_en_fondo(frase=frase_usuario, herramienta=name):
                                        try:
                                            info = neural_learner.registrar_interaccion(frase, herramienta)
                                            log_guardia(f"🧠 {info}")
                                            if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, f"🧠 {info}")
                                        except Exception as e:
                                            log_guardia(f"⚠️ Error entrenando red neuronal: {e}")
                                    threading.Thread(target=entrenar_en_fondo, daemon=True).start()
                                    self.texto_usuario = ""

                                limite = TOOL_TIMEOUTS.get(name, TIMEOUT_HERRAMIENTA)

                                # 🚀 SEGUNDO PLANO: las herramientas lentas (programar/editar
                                # código) no secuestran la conversación. Se responde al momento
                                # que la tarea quedó lanzada y, cuando termina DE VERDAD,
                                # _avisar_tareas inyecta el resultado para que I.R.I.S lo
                                # anuncie por voz, esté el usuario en lo que esté.
                                if name in TOOL_EN_FONDO and name in FUNCIONES_DISPONIBLES:
                                    func = FUNCIONES_DISPONIBLES[name]

                                    async def _trabajo_fondo(nombre=name, funcion=func, argumentos=args, tope=limite):
                                        res = "Error: la tarea fue interrumpida."
                                        try:
                                            if asyncio.iscoroutinefunction(funcion):
                                                res = await asyncio.wait_for(funcion(argumentos), timeout=tope)
                                            else:
                                                res = await asyncio.wait_for(asyncio.to_thread(funcion, argumentos), timeout=tope)
                                        except asyncio.TimeoutError:
                                            # La espera se cancela, pero el hilo HTTP sigue vivo:
                                            # el archivo podría aparecer solo minutos después.
                                            res = (f"Error: tardó más de {tope:.0f} segundos y se canceló la espera. "
                                                   "ADVERTENCIA: el trabajo podría completarse solo más tarde; "
                                                   "que el usuario lo verifique antes de repetir la orden.")
                                        except Exception as e:
                                            res = f"Error: {e}"
                                        finally:
                                            # El aviso se encola ANTES de bajar el contador: si un
                                            # reinicio espera "cero tareas vivas", debe encontrar
                                            # este resultado ya en la cola, nunca perderlo.
                                            try:
                                                await self.avisos_queue.put((nombre, str(res)))
                                            finally:
                                                self._tareas_fondo_activas -= 1

                                    self._tareas_fondo_activas += 1
                                    t = asyncio.create_task(_trabajo_fondo())
                                    # Referencia fuerte: el event loop solo guarda débiles y
                                    # el recolector podría matar la tarea a medio trabajo.
                                    self._tareas_fondo.add(t)
                                    t.add_done_callback(self._tareas_fondo.discard)
                                    log_guardia(f"🚀 {name} lanzada en SEGUNDO PLANO (límite {limite:.0f}s). La conversación sigue libre.")
                                    if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, f"🚀 {name} trabajando en segundo plano...")

                                    kwargs_fr = {"name": name, "response": {"result": (
                                        f"TAREA INICIADA en segundo plano (puede tardar hasta {max(1, int(limite // 60))} minutos). "
                                        "Dile al usuario con una frase corta que ya estás trabajando en ello y que le avisarás "
                                        "en cuanto esté lista. Mientras tanto sigues disponible para cualquier otra orden. "
                                        "NO vuelvas a llamar esta herramienta para esta misma petición.")}}
                                    if getattr(fc, "id", None): kwargs_fr["id"] = fc.id
                                    respuestas_herramientas.append(types.FunctionResponse(**kwargs_fr))
                                    continue

                                try:
                                    if name in FUNCIONES_DISPONIBLES:
                                        func = FUNCIONES_DISPONIBLES[name]
                                        if asyncio.iscoroutinefunction(func):
                                            resultado = await asyncio.wait_for(func(args), timeout=limite)
                                        else:
                                            resultado = await asyncio.wait_for(asyncio.to_thread(func, args), timeout=limite)
                                    else:
                                        resultado = f"No registrada: {name}"
                                except asyncio.TimeoutError:
                                    log_guardia(f"⏱️ {name} superó su límite de {limite:.0f}s.")
                                    resultado = (f"Error: la herramienta tardó más de {limite:.0f} segundos y se "
                                                 "canceló la espera. Informa al usuario con honestidad.")
                                except Exception as err:
                                    resultado = f"Error: {err}"

                                # El id solo se manda si el servidor dio uno: un id nulo
                                # en la respuesta puede tumbar la sesión entera.
                                kwargs_fr = {"name": name, "response": {"result": str(resultado)}}
                                if getattr(fc, "id", None):
                                    kwargs_fr["id"] = fc.id
                                respuestas_herramientas.append(types.FunctionResponse(**kwargs_fr))

                            await session.send_tool_response(function_responses=respuestas_herramientas)
                            if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Analizando datos...")
                        except Exception:
                            # Si esto falla, el servidor queda esperando la respuesta de la
                            # herramienta y cierra la sesión: dejarlo en silencio nos tuvo
                            # una tarde entera sin saber por qué se caía la conexión.
                            log_guardia(f"❌ Error enviando respuesta de herramienta a Gemini:\n{traceback.format_exc()}")
                            
                    asyncio.create_task(ejecutar_herramientas(response.tool_call.function_calls))

                # Extra de seguridad: Si la red completa un turno SIN AUDIO (Puro texto)
                if response.server_content and response.server_content.turn_complete:
                    # 🏁 El servidor confirma que el turno acabó: la transcripción está
                    # completa y _play_audio ya puede evaluar pregunta/afirmación.
                    self._turno_completo = True
                    if self.audio_in_queue.empty() and self.estado != "HABLANDO":
                        self.evaluar_texto_y_estado()

        except websockets.exceptions.ConnectionClosedError as e:
            log_guardia(f"🔌 Conexión con Gemini cerrada (recepción): code={getattr(e, 'code', '?')} reason={getattr(e, 'reason', '')!r} {e}")
            return
        except asyncio.TimeoutError:
            log_guardia("🔌 Timeout en la recepción de Gemini.")
            return
        except Exception:
            log_guardia(f"❌ Error procesando mensajes de Gemini (la sesión se reiniciará):\n{traceback.format_exc()}")
            return

    async def _avisar_tareas(self):
        """📬 El mensajero de las tareas en segundo plano.

        Espera los resultados que dejan las herramientas lanzadas en fondo
        (auto_programmer, self_edit) y los inyecta en la sesión Live como aviso
        interno: I.R.I.S los anuncia por voz al instante, sin importar qué esté
        haciendo el usuario. Si la herramienta creó o cambió código, recarga el
        catálogo y renueva la sesión para que Gemini ya la tenga disponible.
        Si el cambio fue en el núcleo (ui.py, main.py), el reinicio se hace AQUÍ,
        cuando I.R.I.S termina de hablar, nunca a mitad de la frase.
        """
        while True:
            nombre, resultado = await self.avisos_queue.get()
            reinicio = await self._procesar_aviso(nombre, resultado)
            if reinicio:
                await self._reiniciar_tras_hablar()

    async def _procesar_aviso(self, nombre, resultado):
        """Entrega un aviso al modelo. Devuelve True si el cambio exige reiniciar."""
        reinicio = "[REINICIO_REQUERIDO]" in resultado
        resultado = resultado.replace("[REINICIO_REQUERIDO]", "").strip()

        log_guardia(f"📬 Tarea en segundo plano terminada: {nombre} → {resultado[:150]}")
        if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, f"📬 {nombre} terminó: {resultado[:90]}")
        try:
            import winsound
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception: pass

        exito = not resultado.lower().startswith("error")

        # Tras terminar una tarea de fondo, cualquier repetición que pida el usuario
        # ("inténtalo de nuevo") es intencional: que el anti-eco no se la trague.
        self._ultima_llamada = None

        texto = (
            "[AVISO INTERNO DEL SISTEMA — esto NO lo dijo el usuario] La tarea en segundo plano "
            f"'{nombre}' acaba de terminar. Resultado: {resultado} — Anúncialo AHORA al usuario "
            "con una frase breve y natural en español; si fue un error, dilo con honestidad."
        )
        for intento in range(60):  # hasta ~2 min esperando una sesión viva donde entregarlo
            ses = self.session_actual
            # 🕐 Cortesía (máx ~1 min): si I.R.I.S está hablando, escuchando tu
            # respuesta a una pregunta, o grabando tu huella, el aviso espera un
            # hueco; interrumpir cerraría el micrófono en la cara del usuario o
            # colaría la voz TTS dentro de la grabación de la huella.
            ocupado = self.estado in ("ESCUCHANDO", "HABLANDO", "ENROLANDO") and intento < 30
            if ses is not None and not ocupado:
                try:
                    await ses.send_client_content(
                        turns=types.Content(role="user", parts=[types.Part.from_text(text=texto)]),
                        turn_complete=True)
                    break
                except Exception as e:
                    log_guardia(f"⚠️ Aviso de '{nombre}' no entregado aún ({e}). Reintento...")
            await asyncio.sleep(2)
        else:
            log_guardia(f"❌ No pude entregar el aviso de '{nombre}' a ninguna sesión en 2 minutos.")

        if exito and nombre in ("auto_programmer", "self_edit") and not reinicio:
            # Nació o cambió una herramienta de actions/: PRIMERO se deja que
            # I.R.I.S termine de hablar el anuncio y LUEGO se recarga el catálogo
            # y se renueva la sesión. (Renovar antes mataba la sesión vieja con el
            # anuncio a medio decir: el famoso corte a mitad de frase.)
            await self._esperar_anuncio_hablado()
            try:
                # En un hilo aparte: el reload en frío tarda ~0.5s y dentro del
                # event loop congelaba la bocina y el envío de audio (lag audible).
                await asyncio.to_thread(auto_descubrir_herramientas)
                self._renovar_sesion.set()
            except Exception as e:
                log_guardia(f"⚠️ No pude recargar el catálogo de herramientas: {e}")

        return reinicio and exito

    async def _esperar_anuncio_hablado(self, max_inicio_seg=15):
        """Espera a que el anuncio EMPIECE a sonar (máx unos segundos) y termine."""
        for _ in range(int(max_inicio_seg * 10)):
            if self.estado == "HABLANDO":
                break
            await asyncio.sleep(0.1)
        await self._esperar_fin_de_habla()

    async def _esperar_fin_de_habla(self, max_seg=120):
        """Espera a que I.R.I.S termine FÍSICAMENTE de hablar (bocina vacía)."""
        for _ in range(int(max_seg * 10)):
            if self.estado != "HABLANDO" and self.audio_in_queue.empty():
                return
            await asyncio.sleep(0.1)

    async def _reiniciar_tras_hablar(self):
        """🔄 Reinicio educado del núcleo: primero se termina de hablar, luego se
        reinicia, y la conversación CONTINÚA tras el reinicio.

        El método anterior (un temporizador ciego dentro de self_edit) mataba el
        proceso a los pocos segundos: cortaba el anuncio de I.R.I.S a media frase
        y la conversación se perdía entera.
        """
        log_guardia("⏳ Reinicio pendiente: esperando a que I.R.I.S termine de anunciarlo...")

        # 1-2. Que el anuncio EMPIECE a sonar y TERMINE del todo
        await self._esperar_anuncio_hablado(max_inicio_seg=20)

        # 3. Si quedan tareas de fondo vivas, se les da tiempo (máx 5 min) y sus
        #    avisos pendientes se entregan y se terminan de hablar antes de morir.
        espera = 0
        while self._tareas_fondo_activas > 0 and espera < 300:
            await asyncio.sleep(1.0)
            espera += 1
        while not self.avisos_queue.empty():
            try:
                n, r = self.avisos_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            await self._procesar_aviso(n, r)   # los reinicios anidados dan igual: ya vamos a reiniciar
            await self._esperar_fin_de_habla()

        await asyncio.sleep(1.0)  # margen para el último trozo de audio en la bocina

        # 4. Guardar el asa de reanudación: el proceso nuevo retoma ESTA conversación.
        try:
            with open(os.path.join("config", "session_reanudar.json"), "w", encoding="utf-8") as f:
                json.dump({"handle": self._resumption_handle, "ts": time.time()}, f)
        except Exception as e:
            log_guardia(f"⚠️ No pude guardar el asa de reanudación: {e}")

        log_guardia("🔄 Reiniciando la interfaz para aplicar los cambios del núcleo...")
        import subprocess
        subprocess.Popen([sys.executable] + sys.argv)
        os._exit(0)

    async def _play_audio(self):
        stream = None
        try:
            stream = sd.RawOutputStream(device=self.spk_idx, samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16")
        except:
            stream = sd.RawOutputStream(samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16")

        if stream is not None:
            with stream:
                stream.start()
                ultimo_nivel_voz = 0.0
                while True:
                    chunk = await self.audio_in_queue.get()

                    # La grabación de la huella (ENROLANDO) no se interrumpe por audio tardío
                    if self.estado not in ("HABLANDO", "ENROLANDO"):
                        self.estado = "HABLANDO"
                        self.actualizar_ui()

                    # 🎤→✨ Nivel real de la voz de I.R.I.S. para la animación del HUD
                    # (throttle a ~20/s; el cálculo es un rms barato por trozo)
                    try:
                        ahora = time.monotonic()
                        if ahora - ultimo_nivel_voz > 0.05 and hasattr(self.ui.puente, 'senal_voz'):
                            muestras = np.frombuffer(chunk, dtype=np.int16)
                            if muestras.size:
                                rms_voz = float(np.sqrt(np.mean(muestras.astype(np.float64) ** 2)))
                                self.ui.puente.senal_voz.emit(min(1.0, rms_voz / 32768.0 * 6.0))
                            ultimo_nivel_voz = ahora
                    except Exception: pass

                    await asyncio.to_thread(stream.write, chunk)

                    if self.audio_in_queue.empty():
                        # 🟢 LA SINCRONIZACIÓN PERFECTA:
                        # Esperamos medio segundo de gracia por si vienen más pedazos de audio
                        await asyncio.sleep(0.5)
                        if self.audio_in_queue.empty() and self.estado != "ENROLANDO":
                            # ⏳ Antes de evaluar, esperamos (máx 2s) la confirmación de
                            # fin de turno del servidor: la transcripción puede llegar
                            # DESPUÉS del último trozo de audio, y evaluar sin ella
                            # clasificaba preguntas como turnos vacíos.
                            for _ in range(20):
                                if self._turno_completo or not self.audio_in_queue.empty():
                                    break
                                await asyncio.sleep(0.1)
                            if self.audio_in_queue.empty() and self.estado != "ENROLANDO":
                                # La voz calló: la animación de habla vuelve a reposo
                                try:
                                    if hasattr(self.ui.puente, 'senal_voz'):
                                        self.ui.puente.senal_voz.emit(0.0)
                                except Exception: pass
                                # FÍSICAMENTE la bocina ha dejado de emitir sonido.
                                # Este es el momento EXACTO para evaluar la frase completa.
                                self.evaluar_texto_y_estado(tras_audio=True)
        else:
            while True: await asyncio.sleep(1)

    async def run(self):
        self.loop = asyncio.get_running_loop()
        log_guardia("🚀 [RUN] Iniciando ciclo principal asíncrono...")
        
        asyncio.create_task(self._listen_audio())
        asyncio.create_task(self._play_audio())
        asyncio.create_task(self._vigilar_microfono())
        asyncio.create_task(self._avisar_tareas())
        
        # INSTRUCCIÓN PSICOLÓGICA ANTI-SALUDOS
        instruccion_base = (
            "Eres I.R.I.S., la asistente de inteligencia artificial personal y exclusiva creada por Jonathan. "
            "Tu personalidad es cálida, elegante, ingeniosa y extremadamente natural; te comunicas como una compañera "
            "brillante, no como un sistema robótico. Estás conectada a él mediante un intercomunicador de voz continuo.\n\n"
            "Para que la sincronización técnica entre ustedes fluya perfectamente, sigue estas directrices:\n"
            "- Comunícate de forma útil, concisa y fluida, siempre en español.\n"
            "- Si Jonathan requiere tu atención y solamente dice tu nombre ('Iris', 'oye Iris'), TIENES PROHIBIDO saludar "
            "('hola', 'dime'). Simplemente quédate en absoluto silencio (texto vacío); él sabrá que ya lo estás escuchando.\n"
            "- El hardware de tu micrófono reacciona a tu ortografía. Si necesitas que Jonathan te conteste, ES OBLIGATORIO "
            "usar signos de interrogación (¿?) Y formular la pregunta con una palabra interrogativa clara al inicio de la "
            "frase final (qué, cuál, cómo, quieres, deseas, prefieres...). Si solo estás confirmando una acción o dando un "
            "dato final, NO uses signos de interrogación ni frases interrogativas bajo ninguna circunstancia.\n"
            "- Despídete siempre con gracia, pero nunca lo hagas dejando una pregunta abierta."
        )

        nombre_usuario = (self.cfg.get("user_name") or "").strip()
        if nombre_usuario:
            instruccion_base += f"\n- El usuario prefiere que te dirijas a él como '{nombre_usuario}'."

        instruccion_base += (
            "\n- Tienes un cerebro de aprendizaje local (herramienta 'neural_learner'): una red neuronal que "
            "entrena con cada orden que ejecutas. Si el usuario pregunta qué has aprendido o cuánto has aprendido, "
            "usa neural_learner con action 'stats'; si quiere saber qué harías con una frase, usa action 'predict'."
            "\n- Guardián de voz: tras cada respuesta tuya se abre una ventana de unos segundos en la que el usuario "
            "puede seguir dándote órdenes sin decir 'Iris'; su identidad se verifica biométricamente por voz. "
            "Si lo que escuchas es claramente una conversación dirigida a OTRA persona (hablan entre ellos, "
            "te llega charla de fondo, mencionan a otro interlocutor), NO intervengas: responde texto vacío y guarda silencio.\n"
            "- Si el usuario pide que aprendas su voz, que solo le respondas a él, o configurar el guardián, usa la "
            "herramienta 'voice_guard' (action 'enroll' para grabar su huella, 'status', 'enable', 'disable', 'delete'). "
            "Tras llamar 'enroll', repite sus instrucciones al usuario terminando en afirmación (sin pregunta).\n"
            "- Las herramientas de programación (auto_programmer crea NUEVAS, self_edit edita EXISTENTES) trabajan en "
            "SEGUNDO PLANO: al llamarlas, di brevemente que ya estás trabajando en ello y que avisarás al terminar; "
            "mientras tanto sigue atendiendo cualquier otra orden con normalidad. Cuando recibas un mensaje que empiece "
            "por '[AVISO INTERNO DEL SISTEMA', NO es el usuario hablando: es la señal de que la tarea terminó de verdad; "
            "anuncia su resultado al usuario de inmediato con una frase breve."
        )
        
        while True:
            try:
                while not self.out_queue.empty(): 
                    try: self.out_queue.get_nowait()
                    except asyncio.QueueEmpty: break
                while not self.audio_in_queue.empty(): 
                    try: self.audio_in_queue.get_nowait()
                    except asyncio.QueueEmpty: break
                
                # Reseteo seguro al conectar. Si hay audio del turno anterior aún
                # sonando (HABLANDO), NO machacamos estado ni transcripciones: la
                # reconexión ocurría en plena respuesta y borraba la pregunta que
                # _play_audio estaba a punto de evaluar.
                if self.estado != "HABLANDO":
                    self.estado = "SUSPENSION"
                    self.texto_turno = ""
                    self.texto_transcripcion = ""
                self.texto_usuario = ""
                self._habla_acum = b""
                self._bloques_voz = 0
                self._sil_seguidos = 0
                self._enroll_datos = []

                # Catálogo recalculado en cada conexión: si una tarea en segundo plano
                # creó o editó una herramienta, la sesión renovada ya la incluye.
                version_catalogo = CATALOG_VERSION
                tools = [{"function_declarations": list(TOOL_DECLARATIONS)}] if TOOL_DECLARATIONS else None

                voz = (self.cfg.get("jarvis_voice") or "Aoede").strip()
                config = types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz))),
                    tools=tools,
                    system_instruction=types.Content(parts=[types.Part.from_text(text=instruccion_base)]),
                    # 🟢 Transcripciones oficiales: la de entrada alimenta el aprendizaje
                    # neuronal y la de salida evita que el sistema quede mudo en "HABLANDO".
                    input_audio_transcription=types.AudioTranscriptionConfig(),
                    output_audio_transcription=types.AudioTranscriptionConfig(),
                    # 🔁 Reanudación: si la conexión se cae a mitad de una orden, la
                    # siguiente sesión CONTINÚA la conversación en vez de amnesia total.
                    session_resumption=types.SessionResumptionConfig(handle=self._resumption_handle),
                )

                async with self.client.aio.live.connect(model=MODEL, config=config) as session:
                    reanudada = " (reanudando conversación anterior)" if self._resumption_handle else ""
                    # En una sesión reanudada, la primera llamada de herramienta idéntica
                    # a la última ejecutada se considera un eco y se ignora.
                    self._omitir_repeticion = bool(self._resumption_handle)
                    # El clear solo procede si esta sesión nació con el catálogo al
                    # día: si una tarea de fondo lo cambió DURANTE el handshake,
                    # el evento queda puesto y la renovación se ejecuta enseguida.
                    if CATALOG_VERSION == version_catalogo:
                        self._renovar_sesion.clear()
                    self.session_actual = session
                    log_guardia(f"✅ Conexión con Gemini establecida{reanudada}.")
                    self.actualizar_ui()

                    send_task = asyncio.create_task(self._send_realtime(session))
                    receive_task = asyncio.create_task(self._receive_audio(session))
                    renovar_task = asyncio.create_task(self._renovar_sesion.wait())

                    done, pending = await asyncio.wait([send_task, receive_task, renovar_task],
                                                       return_when=asyncio.FIRST_COMPLETED)

                    self.session_actual = None
                    for task in pending: task.cancel()
                    if renovar_task in done:
                        log_guardia("🔄 Renovando la sesión para cargar el catálogo de herramientas actualizado.")
                    else:
                        for task in done:
                            if task is renovar_task: continue
                            try: task.result()
                            except Exception:
                                log_guardia(f"🔌 La sesión terminó con error:\n{traceback.format_exc()}")
                        log_guardia("🔄 Sesión con Gemini finalizada. Reconectando...")

            except Exception:
                # La conexión no pudo ni abrirse (red, API key, handle caducado...).
                log_guardia(f"🔌 No se pudo conectar con Gemini (reintento en 1s):\n{traceback.format_exc()}")
                # Un handle de reanudación caducado impide conectar: lo soltamos
                # para que el siguiente intento entre con sesión limpia.
                self._resumption_handle = None
                await asyncio.sleep(1.0)

def iniciar_cerebro(ui):
    try:
        IRIS = IRISCore(ui)
        asyncio.run(IRIS.run())
    except Exception as e:
        ui.puente.senal_log.emit(f"SYS Error Fatal")
        log_guardia(f"❌ [FATAL ERROR MAIN THREAD]:\n{traceback.format_exc()}")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    
    try:
        import json
        import os
        if os.path.exists("jarvis_config.json"):
            with open("jarvis_config.json", "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if cfg.get("gpu_acceleration", False): os.environ["QT_OPENGL"] = "desktop"  
                else: os.environ["QT_OPENGL"] = "software" 
    except Exception: pass

    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    app = QApplication.instance() or QApplication(sys.argv)
    
    socket = QLocalSocket()
    socket.connectToServer("IRIS_SingleInstance")
    if socket.waitForConnected(500):
        print("SYS: Ya hay clon. Cerrando.")
        sys.exit(1)
        
    local_server = QLocalServer()
    local_server.listen("IRIS_SingleInstance")
    
    load_dotenv()
    auto_descubrir_herramientas()
            
    ventana = JarvisUI() 
    ventana.puente.senal_log.emit("SYS: Iniciando sistema...")
    ventana._win.show() 
    
    hilo_ia = threading.Thread(target=iniciar_cerebro, args=(ventana,), daemon=True)
    hilo_ia.start()
    
    sys.exit(app.exec())