import warnings
warnings.filterwarnings("ignore")

import asyncio
import json
import sys
import threading
import time
import os
import collections
import importlib
import datetime
import traceback
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
from actions import neural_learner
from actions import voice_guard

SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHANNELS = 1
MODEL = "gemini-3.1-flash-live-preview"
TOOL_DECLARATIONS = []
FUNCIONES_DISPONIBLES = {}

def log_guardia(mensaje):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    linea = f"[{ts}] {mensaje}"
    try:
        print(linea)
    except Exception:
        # Consolas sin UTF-8 no deben tumbar al asistente por un emoji
        try: print(linea.encode("ascii", "replace").decode("ascii"))
        except Exception: pass
    try:
        with open("guardia_log.txt", "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except Exception:
        pass

def auto_descubrir_herramientas():
    log_guardia("⚙️ Descubriendo herramientas en /actions...")
    global TOOL_DECLARATIONS, FUNCIONES_DISPONIBLES
    TOOL_DECLARATIONS.clear()
    FUNCIONES_DISPONIBLES.clear()
    
    if not os.path.exists("actions"):
        os.makedirs("actions")
        return

    for archivo in os.listdir("actions"):
        if archivo.endswith(".py") and archivo != "__init__.py":
            nombre = archivo[:-3] 
            try:
                modulo = importlib.import_module(f"actions.{nombre}")
                importlib.reload(modulo) 
                
                if hasattr(modulo, nombre):
                    FUNCIONES_DISPONIBLES[nombre] = getattr(modulo, nombre)
                if hasattr(modulo, "TOOL_DEF"):
                    TOOL_DECLARATIONS.append(modulo.TOOL_DEF)
            except Exception as e:
                log_guardia(f"⚠️ Error al auto-descubrir '{nombre}':\n{traceback.format_exc()}")
                
    log_guardia(f"⚙️ Herramientas cargadas: {list(FUNCIONES_DISPONIBLES.keys())}")

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
        self._habla_acum = b""         # ráfaga de voz acumulada pendiente de verificar
        self._bloques_voz = 0
        self._sil_seguidos = 0
        self._enroll_datos = []        # audio crudo mientras se graba tu huella
        self._enroll_ini = 0.0

        self.mic_idx = None
        self.spk_idx = None

        try:
            dispositivos = sd.query_devices()

            # 🟢 PRIORIDAD 1: Los dispositivos elegidos en la ventana de Ajustes
            def buscar_por_nombre(nombre_cfg, es_entrada):
                if not nombre_cfg: return None
                objetivo = nombre_cfg.strip().lower()
                for i, d in enumerate(dispositivos):
                    canales = d['max_input_channels'] if es_entrada else d['max_output_channels']
                    if canales > 0 and "MME" in sd.query_hostapis(d['hostapi'])['name']:
                        nombre_dev = d['name'].strip().lower()
                        if objetivo in nombre_dev or nombre_dev in objetivo:
                            return i
                return None

            self.mic_idx = buscar_por_nombre(self.cfg.get("mic_device_name", ""), True)
            self.spk_idx = buscar_por_nombre(self.cfg.get("speaker_device_name", ""), False)

            if self.mic_idx is None:
                for i, d in enumerate(dispositivos):
                    if d['max_input_channels'] > 0 and "MME" in sd.query_hostapis(d['hostapi'])['name']:
                        nombre_mic = d['name'].upper()
                        if "ASTRO" in nombre_mic and "GAME" in nombre_mic:
                            self.mic_idx = i; break
            if self.mic_idx is None:
                for i, d in enumerate(dispositivos):
                    if d['max_input_channels'] > 0 and "MME" in sd.query_hostapis(d['hostapi'])['name']:
                        nombre_mic = d['name'].upper()
                        if "ASTRO" in nombre_mic and "VOICE" not in nombre_mic:
                            self.mic_idx = i; break
            if self.mic_idx is None:
                for i, d in enumerate(dispositivos):
                    if d['max_input_channels'] > 0 and "MME" in sd.query_hostapis(d['hostapi'])['name']:
                        self.mic_idx = i; break
            
            if self.spk_idx is None:
                for i, d in enumerate(dispositivos):
                    if d['max_output_channels'] > 0 and "MME" in sd.query_hostapis(d['hostapi'])['name']:
                        nombre_spk = d['name'].upper()
                        if "ASTRO" in nombre_spk and "GAME" in nombre_spk:
                            self.spk_idx = i; break
            if self.spk_idx is None:
                for i, d in enumerate(dispositivos):
                    if d['max_output_channels'] > 0 and "MME" in sd.query_hostapis(d['hostapi'])['name']:
                        nombre_spk = d['name'].upper()
                        if "ASTRO" in nombre_spk and "VOICE" not in nombre_spk:
                            self.spk_idx = i; break
            if self.spk_idx is None:
                for i, d in enumerate(dispositivos):
                    if d['max_output_channels'] > 0 and "MME" in sd.query_hostapis(d['hostapi'])['name']:
                        self.spk_idx = i; break

            if self.mic_idx is not None: log_guardia(f"⚙️ MICRÓFONO ASIGNADO: {dispositivos[self.mic_idx]['name']}")
            if self.spk_idx is not None: log_guardia(f"⚙️ BOCINA ASIGNADA: {dispositivos[self.spk_idx]['name']}")
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
            # NUNCA nos quedamos atascados: cerramos micrófono y volvemos a guardia.
            if tras_audio or self.estado == "HABLANDO":
                log_guardia("🔇 Turno de voz sin transcripción. Cerrando micrófono por seguridad.")
                self.estado = "SUSPENSION"
                self._reset_recognizer_seguro()
                self.texto_usuario = ""
                self.actualizar_ui()
            return

        log_guardia(f"🔎 Analizando respuesta física de I.R.I.S: '{texto}'")

        if "?" in texto or "¿" in texto:
            log_guardia("❓ PREGUNTA DETECTADA. Manteniendo micrófono abierto.")
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
                        
                vol_max = float(np.max(np.abs(indata.astype(np.int32))))
                nivel = vol_max / 32768.0
                
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

                    # Detector de actividad de voz (piso de ruido adaptativo)
                    rms = float(np.sqrt(np.mean(indata.astype(np.float64) ** 2)))
                    if self._ruido is None: self._ruido = max(rms, 1.0)
                    voz_activa = rms > max(self._ruido * 3.5, 250.0)
                    if not voz_activa:
                        self._ruido = 0.95 * self._ruido + 0.05 * max(rms, 1.0)

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
                            recorte = b"".join(list(self.audio_buffer)[-6:])  # último ~1.5s (incluye el wake-word)
                            ok, sim, seg = voice_guard.verificar_bytes(recorte)
                            if ok is False or (ok is None and voice_guard.modo_estricto()):
                                log_guardia(f"🔒 Wake-word con voz NO reconocida (similitud {sim:.2f}, voz {seg:.1f}s). Ignorado.")
                                with self.vosk_lock:
                                    self.recognizer.Reset()
                            else:
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

        stream = None
        try:
            stream = sd.InputStream(device=self.mic_idx, samplerate=SEND_SAMPLE_RATE, channels=CHANNELS, dtype="int16", blocksize=4000, callback=callback)
        except:
            stream = sd.InputStream(samplerate=SEND_SAMPLE_RATE, channels=CHANNELS, dtype="int16", blocksize=4000, callback=callback)

        if stream is not None:
            with stream:
                while True: await asyncio.sleep(1)
        else:
            while True: await asyncio.sleep(1)

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
        except (websockets.exceptions.ConnectionClosedError, asyncio.TimeoutError): return 
        except Exception: return

    async def _receive_audio(self, session):
        try:
            async for response in session.receive():
                sc = response.server_content

                if sc:
                    # 🧠 Transcripción de TU voz (materia prima del aprendizaje neuronal)
                    it = getattr(sc, 'input_transcription', None)
                    if it and it.text:
                        self.texto_usuario += it.text
                        # 🎙️ Red de seguridad: si pides grabar tu voz, lo agendamos
                        # nosotros mismos aunque el modelo olvide llamar la herramienta.
                        if not voice_guard.enroll_pendiente() and voice_guard.frase_pide_enrolamiento(self.texto_usuario):
                            voice_guard.solicitar_enrolamiento()
                            log_guardia("🎙️ Orden de enrolamiento detectada en tu voz. Se grabará al terminar el turno.")

                    # 🗣️ Transcripción de la voz de I.R.I.S (para evaluar ¿pregunta o afirmación?
                    # incluso cuando el modelo no envía texto en las parts)
                    ot = getattr(sc, 'output_transcription', None)
                    if ot and ot.text:
                        self.texto_transcripcion += ot.text
                        if not self.texto_turno:
                            t = self.texto_transcripcion
                            texto_mostrar = t if len(t) < 70 else "..." + t[-65:]
                            if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_transcripcion.emit, f"IRIS: {texto_mostrar}")

                if sc and sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            self.audio_in_queue.put_nowait(part.inline_data.data)

                        if part.text:
                            # ACUMULAMOS TODO EL TEXTO
                            self.texto_turno += part.text

                            texto_mostrar = self.texto_turno if len(self.texto_turno) < 70 else "..." + self.texto_turno[-65:]
                            if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_transcripcion.emit, f"IRIS: {texto_mostrar}")

                elif getattr(response, 'data', None):
                    self.audio_in_queue.put_nowait(response.data)

                if response.tool_call:
                    async def ejecutar_herramientas(llamadas):
                        try:
                            respuestas_herramientas = []
                            for fc in llamadas:
                                name = fc.name
                                args = dict(fc.args) if fc.args else {}
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

                                try:
                                    if name in FUNCIONES_DISPONIBLES:
                                        func = FUNCIONES_DISPONIBLES[name]
                                        if asyncio.iscoroutinefunction(func):
                                            resultado = await asyncio.wait_for(func(args), timeout=30.0)
                                        else:
                                            resultado = await asyncio.wait_for(asyncio.to_thread(func, args), timeout=30.0)
                                    else:
                                        resultado = f"No registrada: {name}"
                                except asyncio.TimeoutError:
                                    resultado = f"Error: Timeout."
                                except Exception as err:
                                    resultado = f"Error: {err}"

                                respuestas_herramientas.append(types.FunctionResponse(id=fc.id, name=name, response={"result": str(resultado)}))
                            
                            await session.send_tool_response(function_responses=respuestas_herramientas)
                            if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Analizando datos...")
                        except Exception: pass
                            
                    asyncio.create_task(ejecutar_herramientas(response.tool_call.function_calls))

                # Extra de seguridad: Si la red completa un turno SIN AUDIO (Puro texto)
                if response.server_content and response.server_content.turn_complete:
                    if self.audio_in_queue.empty() and self.estado != "HABLANDO":
                        self.evaluar_texto_y_estado()
        
        except (websockets.exceptions.ConnectionClosedError, asyncio.TimeoutError): return
        except Exception: return

    async def _play_audio(self):
        stream = None
        try:
            stream = sd.RawOutputStream(device=self.spk_idx, samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16")
        except:
            stream = sd.RawOutputStream(samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16")

        if stream is not None:
            with stream:
                stream.start()
                while True:
                    chunk = await self.audio_in_queue.get()

                    # La grabación de la huella (ENROLANDO) no se interrumpe por audio tardío
                    if self.estado not in ("HABLANDO", "ENROLANDO"):
                        self.estado = "HABLANDO"
                        self.actualizar_ui()

                    await asyncio.to_thread(stream.write, chunk)

                    if self.audio_in_queue.empty():
                        # 🟢 LA SINCRONIZACIÓN PERFECTA:
                        # Esperamos medio segundo de gracia por si vienen más pedazos de audio
                        await asyncio.sleep(0.5)
                        if self.audio_in_queue.empty() and self.estado != "ENROLANDO":
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
        
        tools = [{"function_declarations": TOOL_DECLARATIONS}] if TOOL_DECLARATIONS else None
        
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
            "usar signos de interrogación (¿?). Si solo estás confirmando una acción o dando un dato final, NO uses signos "
            "de interrogación bajo ninguna circunstancia.\n"
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
            "Tras llamar 'enroll', repite sus instrucciones al usuario terminando en afirmación (sin pregunta)."
        )
        
        while True:
            try:
                while not self.out_queue.empty(): 
                    try: self.out_queue.get_nowait()
                    except asyncio.QueueEmpty: break
                while not self.audio_in_queue.empty(): 
                    try: self.audio_in_queue.get_nowait()
                    except asyncio.QueueEmpty: break
                
                # Reseteo seguro al conectar
                self.estado = "SUSPENSION"
                self.texto_turno = ""
                self.texto_transcripcion = ""
                self.texto_usuario = ""
                self._habla_acum = b""
                self._bloques_voz = 0
                self._sil_seguidos = 0
                self._enroll_datos = []

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
                )
                
                async with self.client.aio.live.connect(model=MODEL, config=config) as session:
                    log_guardia("✅ Conexión con Gemini establecida.")
                    self.actualizar_ui()
                    
                    send_task = asyncio.create_task(self._send_realtime(session))
                    receive_task = asyncio.create_task(self._receive_audio(session))
                    
                    done, pending = await asyncio.wait([send_task, receive_task], return_when=asyncio.FIRST_COMPLETED)
                    
                    for task in pending: task.cancel()
                    for task in done:
                        try: task.result()
                        except Exception: pass
                        
            except Exception: await asyncio.sleep(0.1)

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