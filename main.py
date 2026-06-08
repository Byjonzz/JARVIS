import warnings
warnings.filterwarnings("ignore")

import asyncio
import json
import sys
import threading
import os
import importlib
import datetime
import traceback
import numpy as np
import sounddevice as sd
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
        log_guardia("🧠 [INIT] Inicializando clase IRISCore (Detección Contextual Pura)...")
        self.ui = ui
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.texto_respuesta = ""
        self.is_speaking_ui = False
        self.tool_in_progress = False
        self.mic_abierto = True  # Inicia alerta
        
        self.mic_idx = None
        self.spk_idx = None
        
        self.audio_in_queue = asyncio.Queue()
        self.out_queue = asyncio.Queue()
        log_guardia("🧠 [INIT] Clase IRISCore inicializada al 100%.")

    async def _listen_audio(self):
        log_guardia("🎤 Tarea _listen_audio iniciada.")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            if status: pass
            
            try:
                # 1. Visualización (esto siempre debe funcionar)
                vol_max = float(np.max(np.abs(indata)))
                nivel = vol_max / 32768.0
                loop.call_soon_threadsafe(lambda: self.ui._win.orb.set_audio(nivel) if hasattr(self.ui, '_win') else None)
                
                # 2. EL INTERRUPTOR FÍSICO
                # Si el micrófono está cerrado (mic_abierto == False), enviamos SILENCIO
                if not getattr(self, 'mic_abierto', False):
                    # Generamos el mismo tamaño de bytes pero con valores 0
                    silencio = b'\x00' * len(indata.tobytes())
                    loop.call_soon_threadsafe(self.out_queue.put_nowait, silencio)
                else:
                    # Solo si está abierto enviamos tu voz real
                    loop.call_soon_threadsafe(self.out_queue.put_nowait, indata.copy().tobytes())

            except Exception as e:
                log_guardia(f"Error en callback: {e}")

        stream = None
        try:
            stream = sd.InputStream(
                samplerate=SEND_SAMPLE_RATE, channels=CHANNELS, dtype="int16", blocksize=4000, callback=callback
            )
        except Exception as e:
            log_guardia(f"🔥 FATAL: No se pudo inicializar el micrófono predeterminado. {e}")

        if stream is not None:
            with stream:
                while True: await asyncio.sleep(1)
        else:
            while True: await asyncio.sleep(1)

    async def _send_realtime(self, session):
        try:
            while True:
                chunk = await self.out_queue.get()
                data = bytearray(chunk.tobytes())
                while not self.out_queue.empty():
                    try:
                        data.extend(self.out_queue.get_nowait().tobytes())
                    except asyncio.QueueEmpty: break
                
                await session.send_realtime_input(audio=types.Blob(data=bytes(data), mime_type="audio/pcm;rate=16000"))
                await asyncio.sleep(0.01)
        except (websockets.exceptions.ConnectionClosedError, asyncio.TimeoutError): return 
        except Exception: return

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
                        
                        max_retry = 0
                        while not self.out_queue.empty() and max_retry < 50:
                            try: 
                                self.out_queue.get_nowait()
                                max_retry += 1
                            except asyncio.QueueEmpty: break
                        self.tool_in_progress = False
                            
                    asyncio.create_task(ejecutar_herramientas(response.tool_call.function_calls))

                if response.server_content:
                    sc = response.server_content
                    if sc.turn_complete:
                        texto_final = self.texto_respuesta.strip()
                        
                        # Solo analizamos si hay texto real (evita falsos positivos por pausas cortas)
                        if len(texto_final) > 0:
                            if "?" in texto_final or "¿" in texto_final:
                                log_guardia("❓ Respuesta es PREGUNTA. Estado Lógico: ABIERTO.")
                                self.mic_abierto = True
                            else:
                                log_guardia("🔇 Respuesta es AFIRMACIÓN. Estado Lógico: SUSPENSIÓN.")
                                self.mic_abierto = False
                                
                        self.texto_respuesta = "" 
        
        except (websockets.exceptions.ConnectionClosedError, asyncio.TimeoutError): return
        except Exception: return

    async def _play_audio(self):
        loop = asyncio.get_event_loop()
        stream = None
        try:
            stream = sd.RawOutputStream(
                samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16"
            )
        except Exception as e:
            log_guardia(f"🔥 FATAL: No se pudo abrir la bocina predeterminada. {e}")

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
                        
                        # 🟢 ACTUALIZACIÓN VISUAL INMEDIATA AL TERMINAR DE HABLAR
                        if getattr(self, 'mic_abierto', True):
                            loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🌐 ESCUCHANDO")
                            loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Esperando tu respuesta...")
                        else:
                            loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ SUSPENSIÓN")
                            loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Modo reposo. Di 'Iris' para llamar su atención.")
        else:
            while True: await asyncio.sleep(1)

    async def run(self):
        log_guardia("🚀 [RUN] Iniciando ciclo principal asíncrono...")
        
        asyncio.create_task(self._listen_audio())
        asyncio.create_task(self._play_audio())
        
        tools = [{"function_declarations": TOOL_DECLARATIONS}] if TOOL_DECLARATIONS else None
        
        # 🟢 INSTRUCCIÓN PSICOLÓGICA PARA CONTROLAR EL FLUJO ABIERTO
        instruccion_base = (
            "Eres I.R.I.S., una asistente virtual femenina muy avanzada. Tu creador es Jonathan. "
            "Estás operando en un canal de audio continuo 24/7. "
            "REGLAS DE CONVERSACIÓN ESTRICTAS: "
            "1. Responde SIEMPRE con rapidez y naturalidad en español. "
            "2. Si en tu turno anterior NO hiciste una pregunta, asume que la conversación terminó y DEBES IGNORAR POR COMPLETO el ruido ambiental, televisión o conversaciones de Jonathan, a menos que él diga claramente la palabra 'Iris'. "
            "3. Si en tu turno anterior SÍ hiciste una pregunta, presta atención y responde directamente a lo que diga Jonathan sin que él necesite decir 'Iris'. "
            "4. Cuando hagas una pregunta, SIEMPRE utiliza el signo de interrogación (¿ y ?). "
            "5. NUNCA te despidas con una pregunta."
        )
        
        loop = asyncio.get_event_loop()
        
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
                self.texto_respuesta = ""
                
                config = types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede"))),
                    tools=tools,
                    system_instruction=types.Content(parts=[types.Part.from_text(text=instruccion_base)]),
                )
                
                async with self.client.aio.live.connect(model=MODEL, config=config) as session:
                    log_guardia("✅ Conexión con Gemini establecida.")
                    
                    if self.mic_abierto:
                        loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🌐 EN LÍNEA")
                        loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Micrófono abierto. Habla naturalmente.")
                    else:
                        loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ SUSPENSIÓN")
                        loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Modo reposo. Di 'Iris' para llamar su atención.")
                    
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
        print("SYS: Ya hay una instancia en ejecución. Cerrando clon.")
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