import warnings
warnings.filterwarnings("ignore")

import asyncio
import json
import sys
import threading
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

SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHANNELS = 1
MODEL = "gemini-3.1-flash-live-preview"
TOOL_DECLARATIONS = []
FUNCIONES_DISPONIBLES = {}

def log_guardia(mensaje):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    linea = f"[{ts}] {mensaje}"
    print(linea)
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
        log_guardia("🧠 [INIT] Inicializando clase IRISCore (Cronómetro de Silencio)...")
        self.ui = ui
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
        self.texto_acumulado = "" 
        self.tiempo_ultimo_texto = datetime.datetime.now() # 🟢 CRONÓMETRO
        self.evaluando_turno = False
        
        self.is_speaking_ui = False
        self.tool_in_progress = False
        self.mic_abierto = False 
        self.loop = None 
        
        self.mic_idx = None
        self.spk_idx = None
        
        try:
            dispositivos = sd.query_devices()
            for i, d in enumerate(dispositivos):
                if d['max_input_channels'] > 0:
                    api_name = sd.query_hostapis(d['hostapi'])['name']
                    if "MME" in api_name:
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
            
            for i, d in enumerate(dispositivos):
                if d['max_output_channels'] > 0:
                    api_name = sd.query_hostapis(d['hostapi'])['name']
                    if "MME" in api_name:
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

    def actualizar_ui_estado(self):
        if not self.loop: return
        
        if getattr(self, 'mic_abierto', False):
            self.loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🌐 ESCUCHANDO")
            self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Micrófono abierto. Esperando tu respuesta...")
        else:
            self.loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ SUSPENSIÓN")
            self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Micrófono desactivado, vuelve a decir Iris para llamar su atención")

    # 🟢 LA NUEVA FUNCIÓN VIGILANTE POR TIEMPO
    async def _vigilante_silencio(self):
        while True:
            await asyncio.sleep(0.5) # Revisa cada medio segundo
            
            # Si hay texto acumulado y han pasado 3 segundos desde la última letra recibida
            if len(self.texto_acumulado) > 0 and not self.evaluando_turno:
                tiempo_sin_texto = (datetime.datetime.now() - self.tiempo_ultimo_texto).total_seconds()
                
                # Si han pasado 3 segundos sin texto nuevo, significa que I.R.I.S terminó de hablar
                if tiempo_sin_texto > 3.0:
                    self.evaluando_turno = True
                    texto = self.texto_acumulado.strip()
                    log_guardia(f"🔎 Silencio de 3s detectado. Analizando frase final: '{texto}'")
                    
                    if "?" in texto or "¿" in texto:
                        log_guardia(f"❓ PREGUNTA DETECTADA. Micrófono MANTIENE ABIERTO.")
                        self.mic_abierto = True
                    else:
                        log_guardia(f"🔇 AFIRMACIÓN DETECTADA. CERRANDO micrófono.")
                        self.mic_abierto = False
                        if hasattr(self, 'recognizer'):
                            self.recognizer.Reset()
                            
                    # Limpiamos todo para el siguiente turno
                    self.texto_acumulado = ""
                    self.evaluando_turno = False
                    self.actualizar_ui_estado()

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
                        
                vol_max = float(np.max(np.abs(indata)))
                nivel = vol_max / 32768.0
                
                if self.loop: self.loop.call_soon_threadsafe(safe_update_audio)
                
                data_bytes = bytes(indata)
                
                if getattr(self, 'is_speaking_ui', False) or getattr(self, 'tool_in_progress', False):
                    if self.loop: self.loop.call_soon_threadsafe(self.out_queue.put_nowait, b'\x00' * len(data_bytes))
                    return

                if not getattr(self, 'mic_abierto', False):
                    if self.loop: self.loop.call_soon_threadsafe(self.out_queue.put_nowait, b'\x00' * len(data_bytes))
                    
                    self.audio_buffer.append(data_bytes)
                    if self.recognizer.AcceptWaveform(data_bytes):
                        res = json.loads(self.recognizer.Result())
                        texto = res.get("text", "").lower()
                    else:
                        res = json.loads(self.recognizer.PartialResult())
                        texto = res.get("partial", "").lower()
                        
                    palabras_detectadas = set(texto.replace(",", "").replace(".", "").split())
                    
                    if self.WAKE_WORDS.intersection(palabras_detectadas):
                        self.recognizer.Reset()
                        self.mic_abierto = True
                        # 🟢 Bloqueamos evaluación para no chocar con el vigilante
                        self.evaluando_turno = True 
                        self.texto_acumulado = ""
                        self.evaluando_turno = False
                        
                        log_guardia(f"✨ Vosk escuchó Wake-word. Abriendo micrófono.")
                        try:
                            import winsound
                            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
                        except: pass
                        
                        self.actualizar_ui_estado()
                        
                        if self.loop:
                            for chunk in self.audio_buffer:
                                self.loop.call_soon_threadsafe(self.out_queue.put_nowait, chunk)
                        self.audio_buffer.clear()
                else:
                    if self.loop: self.loop.call_soon_threadsafe(self.out_queue.put_nowait, data_bytes)

            except Exception as e:
                pass

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
                if response.server_content and response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            self.audio_in_queue.put_nowait(part.inline_data.data)
                        
                        if part.text:
                            # 🟢 Reiniciamos el cronómetro cada vez que llega una letra nueva
                            self.tiempo_ultimo_texto = datetime.datetime.now()
                            self.texto_acumulado += part.text
                            
                            texto_mostrar = self.texto_acumulado if len(self.texto_acumulado) < 70 else "..." + self.texto_acumulado[-65:]
                            if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_transcripcion.emit, f"IRIS: {texto_mostrar}")
                                
                elif getattr(response, 'data', None):
                    self.audio_in_queue.put_nowait(response.data)

                if response.tool_call:
                    self.tool_in_progress = True
                    async def ejecutar_herramientas(llamadas):
                        try:
                            respuestas_herramientas = []
                            for fc in llamadas:
                                name = fc.name
                                args = dict(fc.args) if fc.args else {}
                                log_guardia(f"⚙️ Ejecutando herramienta: {name}")
                                if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, f"⚙️ Ejecutando: {name}...")

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
                        finally:
                            while not self.out_queue.empty():
                                try: self.out_queue.get_nowait()
                                except asyncio.QueueEmpty: break
                            self.tool_in_progress = False
                            
                    asyncio.create_task(ejecutar_herramientas(response.tool_call.function_calls))
        
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
                    
                    if not getattr(self, 'is_speaking_ui', False):
                        self.is_speaking_ui = True
                        if self.loop: self.loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🗣️ HABLANDO...")
                    
                    await asyncio.to_thread(stream.write, chunk)
                    
                    if self.audio_in_queue.empty():
                        self.is_speaking_ui = False
                        
        else:
            while True: await asyncio.sleep(1)

    async def run(self):
        self.loop = asyncio.get_event_loop() 
        log_guardia("🚀 [RUN] Iniciando ciclo principal asíncrono...")
        
        asyncio.create_task(self._listen_audio())
        asyncio.create_task(self._play_audio())
        asyncio.create_task(self._vigilante_silencio()) # 🟢 NUEVO HILO VIGILANTE
        
        tools = [{"function_declarations": TOOL_DECLARATIONS}] if TOOL_DECLARATIONS else None
        
        instruccion_base = (
            "Eres I.R.I.S., una asistente virtual femenina muy avanzada. Tu creador es Jonathan. "
            "Estás operando en una llamada de audio continua. "
            "REGLAS DE INTERACCIÓN: "
            "1. Responde SIEMPRE con rapidez y naturalidad en español. Sé concisa y amable. "
            "2. OBLIGATORIO: Cuando hagas una pregunta al usuario, SIEMPRE utiliza el signo de interrogación (¿ y ?). Si tu respuesta es una afirmación o dato final, NO uses signos de interrogación. "
            "3. Nunca te despidas con una pregunta. "
            "4. REGLA ESTRICTA DE SILENCIO INICIAL: Si el usuario SOLAMENTE dice tu nombre ('Iris', 'oye Iris', etc.) para llamar tu atención, TIENES ESTRICTAMENTE PROHIBIDO RESPONDER. No digas 'Hola', ni 'Dime'. Mantente en silencio absoluto y espera a que el usuario dicte su orden."
        )
        
        while True:
            try:
                while not self.out_queue.empty(): 
                    try: self.out_queue.get_nowait()
                    except asyncio.QueueEmpty: break
                while not self.audio_in_queue.empty(): 
                    try: self.audio_in_queue.get_nowait()
                    except asyncio.QueueEmpty: break
                
                self.tool_in_progress = False
                self.is_speaking_ui = False
                
                # Reseteamos vigilante
                self.texto_acumulado = "" 
                self.evaluando_turno = False
                
                config = types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede"))),
                    tools=tools,
                    system_instruction=types.Content(parts=[types.Part.from_text(text=instruccion_base)]),
                )
                
                async with self.client.aio.live.connect(model=MODEL, config=config) as session:
                    log_guardia("✅ Conexión con Gemini establecida.")
                    self.actualizar_ui_estado()
                    
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