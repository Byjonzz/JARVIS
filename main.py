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
        log_guardia("🧠 [INIT] Inicializando clase IRISCore (Vosk Gatekeeper Activo)...")
        self.ui = ui
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.texto_respuesta = ""
        self.is_speaking_ui = False
        self.tool_in_progress = False
        self.mic_abierto = False # 🟢 EL CADENERO
        
        self.mic_idx = None
        self.spk_idx = None
        
        try:
            dispositivos = sd.query_devices()
            
            # Buscar Micrófono
            for i, d in enumerate(dispositivos):
                if d['max_input_channels'] > 0:
                    api_name = sd.query_hostapis(d['hostapi'])['name']
                    if "MME" in api_name:
                        nombre_mic = d['name'].upper()
                        if "ASTRO" in nombre_mic and "GAME" in nombre_mic:
                            self.mic_idx = i
                            break
            
            if self.mic_idx is None:
                for i, d in enumerate(dispositivos):
                    if d['max_input_channels'] > 0 and "MME" in sd.query_hostapis(d['hostapi'])['name']:
                        nombre_mic = d['name'].upper()
                        if "ASTRO" in nombre_mic and "VOICE" not in nombre_mic:
                            self.mic_idx = i
                            break
            if self.mic_idx is None:
                for i, d in enumerate(dispositivos):
                    if d['max_input_channels'] > 0 and "MME" in sd.query_hostapis(d['hostapi'])['name']:
                        self.mic_idx = i
                        break
            
            # Buscar Bocina
            for i, d in enumerate(dispositivos):
                if d['max_output_channels'] > 0:
                    api_name = sd.query_hostapis(d['hostapi'])['name']
                    if "MME" in api_name:
                        nombre_spk = d['name'].upper()
                        if "ASTRO" in nombre_spk and "GAME" in nombre_spk:
                            self.spk_idx = i
                            break
            
            if self.spk_idx is None:
                for i, d in enumerate(dispositivos):
                    if d['max_output_channels'] > 0 and "MME" in sd.query_hostapis(d['hostapi'])['name']:
                        nombre_spk = d['name'].upper()
                        if "ASTRO" in nombre_spk and "VOICE" not in nombre_spk:
                            self.spk_idx = i
                            break
            if self.spk_idx is None:
                for i, d in enumerate(dispositivos):
                    if d['max_output_channels'] > 0 and "MME" in sd.query_hostapis(d['hostapi'])['name']:
                        self.spk_idx = i
                        break

            if self.mic_idx is not None:
                log_guardia(f"⚙️ MICRÓFONO ASIGNADO (MME): {dispositivos[self.mic_idx]['name']} (ID: {self.mic_idx})")
            else:
                log_guardia("⚠️ No se encontró controlador MME. Se usará el Default de Windows.")
                
            if self.spk_idx is not None:
                log_guardia(f"⚙️ BOCINA ASIGNADA (MME): {dispositivos[self.spk_idx]['name']} (ID: {self.spk_idx})")

        except Exception as e:
            log_guardia(f"⚠️ Fallo al leer hardware de audio. Error: {e}")
            
        log_guardia("🧠 [INIT] Cargando modelo Vosk para STT local...")
        SetLogLevel(-1)
        self.vosk_model = Model("vosk_model")
        self.recognizer = KaldiRecognizer(self.vosk_model, SEND_SAMPLE_RATE)
        self.ALIAS = ["iris", "yris", "iriz", "yriz", "jarvis", "yarbis", "yarvis"]
        self.audio_buffer = collections.deque(maxlen=15)
        
        self.audio_in_queue = asyncio.Queue()
        self.out_queue = asyncio.Queue()
        log_guardia("🧠 [INIT] Clase IRISCore inicializada al 100%.")

    async def _listen_audio(self):
        log_guardia("🎤 Tarea _listen_audio iniciada.")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            if status:
                pass
            
            try:
                def safe_update_audio():
                    try:
                        if hasattr(self.ui, '_win') and getattr(self.ui._win, 'orb', None):
                            self.ui._win.orb.set_audio(nivel)
                    except RuntimeError:
                        pass
                        
                vol_max = float(np.max(np.abs(indata)))
                nivel = vol_max / 32768.0
                loop.call_soon_threadsafe(safe_update_audio)
                
                data_bytes = bytes(indata)
                
                # Si ella está hablando o trabajando, inyectamos ceros ciegos a Google
                if getattr(self, 'is_speaking_ui', False) or getattr(self, 'tool_in_progress', False):
                    loop.call_soon_threadsafe(self.out_queue.put_nowait, b'\x00' * len(data_bytes))
                    return

                # 🟢 LÓGICA VOSK (EL CADENERO)
                if not self.mic_abierto:
                    self.audio_buffer.append(data_bytes)
                    
                    if self.recognizer.AcceptWaveform(data_bytes):
                        res = json.loads(self.recognizer.Result())
                        texto = res.get("text", "").lower()
                    else:
                        res = json.loads(self.recognizer.PartialResult())
                        texto = res.get("partial", "").lower()
                        
                    if any(alias in texto for alias in self.ALIAS):
                        self.mic_abierto = True
                        log_guardia("✨ Wake-word detectado. Abriendo canal a Google...")
                        import winsound
                        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
                        
                        loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🌐 ESCUCHANDO")
                        loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Te escucho...")
                        
                        for chunk in self.audio_buffer:
                            loop.call_soon_threadsafe(self.out_queue.put_nowait, chunk)
                        self.audio_buffer.clear()
                    else:
                        # Mandamos ceros a Google para mantener el Keep-Alive sin que nos escuche
                        loop.call_soon_threadsafe(self.out_queue.put_nowait, b'\x00' * len(data_bytes))
                else:
                    # Micrófono abierto, Google escucha tu voz real
                    loop.call_soon_threadsafe(self.out_queue.put_nowait, data_bytes)

            except Exception as e:
                pass

        stream = None
        try:
            stream = sd.InputStream(
                device=self.mic_idx, samplerate=SEND_SAMPLE_RATE, channels=CHANNELS, dtype="int16", blocksize=4000, callback=callback
            )
        except Exception as e:
            try:
                stream = sd.InputStream(
                    samplerate=SEND_SAMPLE_RATE, channels=CHANNELS, dtype="int16", blocksize=4000, callback=callback
                )
            except Exception as e2:
                log_guardia(f"🔥 FATAL: El sistema está sordo.")

        if stream is not None:
            with stream:
                while True:
                    await asyncio.sleep(1)
        else:
            while True:
                await asyncio.sleep(1)

    async def _send_realtime(self, session):
        try:
            while True:
                chunk = await self.out_queue.get()
                await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
        except websockets.exceptions.ConnectionClosedError:
            return 
        except asyncio.TimeoutError:
            return
        except Exception:
            return

    async def _receive_audio(self, session):
        loop = asyncio.get_event_loop()
        try:
            async for response in session.receive():
                if response.server_content and response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            self.audio_in_queue.put_nowait(part.inline_data.data)
                        
                        if part.text:
                            self.texto_respuesta += part.text
                            texto_mostrar = self.texto_respuesta if len(self.texto_respuesta) < 70 else "..." + self.texto_respuesta[-65:]
                            loop.call_soon_threadsafe(self.ui.puente.senal_transcripcion.emit, f"IRIS: {texto_mostrar}")
                                
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
                                loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, f"⚙️ Ejecutando: {name}...")

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
                                    resultado = f"Error: La búsqueda tardó demasiado."
                                except Exception as err:
                                    resultado = f"Error interno: {err}"

                                respuestas_herramientas.append(types.FunctionResponse(id=fc.id, name=name, response={"result": str(resultado)}))
                            
                            await session.send_tool_response(function_responses=respuestas_herramientas)
                            loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Analizando datos...")
                            
                        except Exception as crit:
                            log_guardia(f"🔥 Error en herramientas:\n{traceback.format_exc()}")
                        finally:
                            while not self.out_queue.empty():
                                try: self.out_queue.get_nowait()
                                except asyncio.QueueEmpty: break
                            self.tool_in_progress = False
                            
                    asyncio.create_task(ejecutar_herramientas(response.tool_call.function_calls))

                if response.server_content:
                    sc = response.server_content
                    if sc.turn_complete:
                        # 🟢 LA LÓGICA DE CIERRE INTELIGENTE
                        texto_limpio = self.texto_respuesta.strip()
                        if "?" in texto_limpio or "¿" in texto_limpio:
                            log_guardia("❓ I.R.I.S. hizo una pregunta. (Micrófono se queda Abierto)")
                            self.mic_abierto = True
                            loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🌐 ESCUCHANDO")
                            loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Esperando tu respuesta...")
                        else:
                            log_guardia("🔇 Respuesta afirmativa. Cerrando micrófono local.")
                            self.mic_abierto = False
                            self.recognizer.Reset()
                            self.audio_buffer.clear()
                            loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ SUSPENSIÓN")
                            loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Di 'Iris' para activar.")
                        
                        self.texto_respuesta = "" 
        
        except websockets.exceptions.ConnectionClosedError:
            return
        except asyncio.TimeoutError:
            return
        except Exception as e:
            return

    async def _play_audio(self):
        loop = asyncio.get_event_loop()
        stream = None
        try:
            stream = sd.RawOutputStream(
                device=self.spk_idx, samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16"
            )
        except Exception as e:
            try:
                stream = sd.RawOutputStream(
                    samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16"
                )
            except Exception as e2:
                log_guardia(f"🔥 FATAL: No se pudo abrir NINGUNA bocina.")

        if stream is not None:
            with stream:
                stream.start()
                while True:
                    chunk = await self.audio_in_queue.get()
                    
                    if not getattr(self, 'is_speaking_ui', False):
                        self.is_speaking_ui = True
                        loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🗣️ HABLANDO...")
                    
                    await asyncio.to_thread(stream.write, chunk)
                    
                    if self.audio_in_queue.empty():
                        self.is_speaking_ui = False
                        
                        # Al terminar de hablar, actualizamos UI según el estado del micro
                        if getattr(self, 'mic_abierto', False):
                            loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🌐 ESCUCHANDO")
                            loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Esperando tu respuesta...")
                        else:
                            loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ SUSPENSIÓN")
                            loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Di 'Iris' para activar.")
        else:
            while True:
                await asyncio.sleep(1)

    async def run(self):
        log_guardia("🚀 [RUN] Iniciando ciclo principal asíncrono...")
        
        asyncio.create_task(self._listen_audio())
        asyncio.create_task(self._play_audio())
        
        tools = [{"function_declarations": TOOL_DECLARATIONS}] if TOOL_DECLARATIONS else None
        
        instruccion_base = (
            "Eres I.R.I.S., una asistente virtual femenina muy avanzada. Tu creador es Jonathan. "
            "Estás operando en un sistema de voz. "
            "REGLAS DE INTERACCIÓN: "
            "1. Responde SIEMPRE con rapidez y naturalidad. "
            "2. Habla siempre en español. Sé concisa, servicial y usa un tono profesional pero amable. "
        )
        
        loop = asyncio.get_event_loop()
        
        while True:
            try:
                # Si Google reconecta, mantenemos el estado del micrófono como estaba.
                while not self.out_queue.empty(): 
                    try: self.out_queue.get_nowait()
                    except asyncio.QueueEmpty: break
                while not self.audio_in_queue.empty(): 
                    try: self.audio_in_queue.get_nowait()
                    except asyncio.QueueEmpty: break
                
                self.tool_in_progress = False
                self.is_speaking_ui = False
                self.texto_respuesta = ""
                
                config = types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede"))),
                    tools=tools,
                    system_instruction=types.Content(parts=[types.Part.from_text(text=instruccion_base)]),
                )
                
                async with self.client.aio.live.connect(model=MODEL, config=config) as session:
                    log_guardia("✅ Conexión con Gemini establecida.")
                    
                    # Refrescar UI sin cambiar el estado de Vosk
                    if self.mic_abierto:
                        loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🌐 ESCUCHANDO")
                        loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Reconexión exitosa. Te escucho...")
                    else:
                        loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ SUSPENSIÓN")
                        loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Di 'Iris' para activar.")
                    
                    send_task = asyncio.create_task(self._send_realtime(session))
                    receive_task = asyncio.create_task(self._receive_audio(session))
                    
                    done, pending = await asyncio.wait([send_task, receive_task], return_when=asyncio.FIRST_COMPLETED)
                    
                    for task in pending: 
                        task.cancel()
                    for task in done:
                        try:
                            task.result()
                        except Exception:
                            pass
                        
            except Exception as e:
                log_guardia("🔄 Reciclando conexión de forma invisible...")
                await asyncio.sleep(0.1)

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
                if cfg.get("gpu_acceleration", False):
                    os.environ["QT_OPENGL"] = "desktop"  
                else:
                    os.environ["QT_OPENGL"] = "software" 
    except Exception:
        pass

    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    
    app = QApplication.instance() or QApplication(sys.argv)
    
    socket = QLocalSocket()
    socket.connectToServer("IRIS_SingleInstance")
    if socket.waitForConnected(500):
        print("SYS: Ya hay una instancia en ejecución. Cerrando clon.")
        sys.exit(1)
        
    local_server = QLocalServer()
    local_server.listen("IRIS_SingleInstance")
    
    if os.path.exists("guardia_log.txt"):
        try: os.remove("guardia_log.txt") 
        except PermissionError: pass 
            
    log_guardia("=======================================")
    log_guardia("🛡️ INICIANDO ARRANQUE DEL SISTEMA IRIS")
    log_guardia("=======================================")
    
    load_dotenv()
    if not os.getenv("GEMINI_API_KEY"):
        log_guardia("❌ Error: No se encontró GEMINI_API_KEY en el archivo .env")
        sys.exit(1)
        
    auto_descubrir_herramientas()
            
    ventana = JarvisUI() 
    
    ventana.puente.senal_log.emit("SYS: Iniciando sistema...")
    
    ventana._win.show() 
    
    hilo_ia = threading.Thread(target=iniciar_cerebro, args=(ventana,), daemon=True)
    hilo_ia.start()
    
    sys.exit(app.exec())