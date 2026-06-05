import warnings
warnings.filterwarnings("ignore")

import asyncio
import json
import queue
import sys
import threading
import os
import collections
import importlib
import datetime
import traceback
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
from google import genai
from google.genai import types
from PyQt6.QtWidgets import QApplication
from dotenv import load_dotenv

from ui import IRISUI

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
        log_guardia("🧠 [INIT] Inicializando clase IRISCore...")
        self.ui = ui
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.memoria_corta = []
        self.mic_abierto = False
        self.is_speaking_ui = False

        
        log_guardia("🧠 [INIT] Cargando modelo Vosk para STT local...")
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
            try:
                data_bytes = bytes(indata)
                
                if getattr(self, 'is_speaking_ui', False):
                    if self.mic_abierto:
                        self.mic_abierto = False
                        self.recognizer.Reset() 
                        self.audio_buffer.clear() 
                    
                    silencio = b'\x00' * len(data_bytes)
                    loop.call_soon_threadsafe(self.out_queue.put_nowait, silencio)
                    return

                if not self.mic_abierto:
                    self.audio_buffer.append(data_bytes)
                    resultado_parcial = json.loads(self.recognizer.PartialResult())
                    texto_parcial = resultado_parcial.get("partial", "").lower()
                    
                    if self.recognizer.AcceptWaveform(data_bytes):
                        resultado_completo = json.loads(self.recognizer.Result())
                        texto_completo = resultado_completo.get("text", "").lower()
                    else:
                        texto_completo = ""

                    if any(alias in texto_parcial for alias in self.ALIAS) or any(alias in texto_completo for alias in self.ALIAS):
                        self.mic_abierto = True
                        log_guardia("✨ Wake-word detectado, abriendo canal hacia Google...")
                        
                        loop.call_soon_threadsafe(self.ui.puente.senal_despertar.emit)
                        import winsound
                        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
                        
                        for chunk in self.audio_buffer:
                            loop.call_soon_threadsafe(self.out_queue.put_nowait, chunk)
                        self.audio_buffer.clear()
                        
                        loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🌐 CONECTADO...")
                        loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Escuchando orden...")
                    else:
                        silencio = b'\x00' * len(data_bytes)
                        loop.call_soon_threadsafe(self.out_queue.put_nowait, silencio)
                else:
                    loop.call_soon_threadsafe(self.out_queue.put_nowait, data_bytes)
            except Exception as e:
                log_guardia(f"🔥 ERROR FATAL EN MICRÓFONO:\n{traceback.format_exc()}")

        stream = sd.InputStream(
            samplerate=SEND_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=2000, 
            callback=callback,
        )
        
        estado_arranque = "🌐 CONECTADO..." if self.mic_abierto else "🛡️ MODO SUSPENSIÓN"
        loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, estado_arranque)
        
        with stream:
            while True:
                await asyncio.sleep(0.1)

    async def _send_realtime(self, session):
        log_guardia("📤 Tarea _send_realtime iniciada.")
        while True:
            chunk = await self.out_queue.get()
            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
            )

    async def _receive_audio(self, session):
        log_guardia("📥 Tarea _receive_audio iniciada.")
        loop = asyncio.get_event_loop()
        
        async for response in session.receive():
            if response.data:
                self.audio_in_queue.put_nowait(response.data)

            if response.tool_call:
                async def ejecutar_herramientas(llamadas):
                    try:
                        respuestas_herramientas = []
                        for fc in llamadas:
                            name = fc.name
                            args = dict(fc.args) if fc.args else {}
                            log_guardia(f"⚙️ Ejecutando herramienta: {name} con args: {args}")
                            self.ui.puente.senal_log.emit(f"⚙️ Ejecutando: {name}...")

                            resultado = "Error desconocido."
                            try:
                                if name in FUNCIONES_DISPONIBLES:
                                    func = FUNCIONES_DISPONIBLES[name]
                                    if asyncio.iscoroutinefunction(func):
                                        resultado = await asyncio.wait_for(func(args), timeout=15.0)
                                    else:
                                        resultado = await asyncio.wait_for(
                                            asyncio.to_thread(func, args), timeout=15.0
                                        )
                                else:
                                    resultado = f"No registrada: {name}"
                                    
                            except asyncio.TimeoutError:
                                resultado = f"Error: La herramienta '{name}' se congeló y fue abortada."
                                log_guardia(f"⚠️ {resultado}")
                            except Exception as err:
                                log_guardia(f"🔥 ERROR INTERNO EN '{name}':\n{traceback.format_exc()}")
                                resultado = f"Error interno: {err}"

                            resultado_str = str(resultado)
                            log_guardia(f"⚙️ Fin de herramienta {name}.")
                            
                            self.memoria_corta.append(f"Herramienta: {name}. Resultado: {resultado_str[:50]}")
                            if len(self.memoria_corta) > 20: self.memoria_corta.pop(0)

                            respuestas_herramientas.append(
                                types.FunctionResponse(
                                    id=fc.id, name=name, response={"result": resultado_str}
                                )
                            )
                        
                        await asyncio.sleep(0.1)
                        await session.send_tool_response(function_responses=respuestas_herramientas)
                        log_guardia("✅ Respuestas enviadas a Google.")
                        loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Analizando datos...")
                        
                    except Exception as crit:
                        log_guardia(f"🔥 ERROR FATAL AL PROCESAR HERRAMIENTAS:\n{traceback.format_exc()}")

                asyncio.create_task(ejecutar_herramientas(response.tool_call.function_calls))

            if response.server_content:
                sc = response.server_content
                if sc.turn_complete:
                    log_guardia("🏁 Turno completado por Google.")
                    
                    self.mic_abierto = False
                    self.audio_buffer.clear()
                    
                    if self.audio_in_queue.empty() and not getattr(self, 'is_speaking_ui', False):
                        loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ MODO SUSPENSIÓN")
                        loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Sistema en espera.")

    async def _play_audio(self):
        log_guardia("🔊 Tarea _play_audio iniciada.")
        loop = asyncio.get_event_loop()
        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16"
        )
        try:
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
                        loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Sistema en espera.")
                        
                        if getattr(self, 'mic_abierto', False):
                            loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🌐 CONECTADO...")
                        else:
                            loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ MODO SUSPENSIÓN")
        except Exception as e:
            log_guardia(f"🔥 ERROR CRUDO EN _play_audio:\n{traceback.format_exc()}")

    async def run(self):
        log_guardia("🚀 [RUN] Iniciando ciclo principal asíncrono...")
        
        asyncio.create_task(self._listen_audio())
        asyncio.create_task(self._play_audio())
        
        tools = [{"function_declarations": TOOL_DECLARATIONS}] if TOOL_DECLARATIONS else None
        
        instruccion_base = (
            "Eres I.R.I.S., una asistente virtual femenina muy avanzada con arquitectura de IA Local. "
            "Tu creador y administrador es Jonathan (futuro TSU en Desarrollo de Software). "
            "REGLAS DE PERSONALIDAD: Habla en español, sé concisa, elegante, servicial y usa un tono profesional pero amigable. "
            "🛑 REGLA DE DESPEDIDA ESTRICTA: Si Jonathan indica que ya no necesita ayuda, DESPÍDETE SIEMPRE CON UNA AFIRMACIÓN. TIENES ESTRICTAMENTE PROHIBIDO terminar una despedida con una pregunta."
        )
        
        while True:
            try:
                while not self.out_queue.empty(): self.out_queue.get_nowait()
                
                config = types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                        )
                    ),
                    tools=tools,
                    system_instruction=types.Content(parts=[types.Part.from_text(text=instruccion_base)]),
                )

                self.ui.puente.senal_estado.emit("🔌 CONECTANDO...")
                log_guardia("🔌 Intentando conectar con Gemini Live...")
                
                async with self.client.aio.live.connect(model=MODEL, config=config) as session:
                    log_guardia("✅ Conexión con Gemini establecida.")
                    self.ui.puente.senal_estado.emit("🟢 EN LÍNEA")
                    self.ui.puente.senal_log.emit("SYS: Conexión establecida.")
                    
                    send_task = asyncio.create_task(self._send_realtime(session))
                    receive_task = asyncio.create_task(self._receive_audio(session))
                    
                    done, pending = await asyncio.wait(
                        [send_task, receive_task],
                        return_when=asyncio.FIRST_EXCEPTION
                    )
                    
                    for task in pending: task.cancel()
                    for task in done: task.result() 

            except Exception as e:
                self.is_speaking_ui = False 
                self.mic_abierto = False
                self.recognizer.Reset()
                
                log_guardia(f"⚠️ Google cerró la llamada. Reiniciando conexión: {e}")
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "⚠️ RECONECTANDO...")
                loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Restableciendo conexión...")
                await asyncio.sleep(2)

def iniciar_cerebro(ui):
    log_guardia("🧠 [HILO] Hilo iniciar_cerebro lanzado.")
    try:
        IRIS = IRISCore(ui)
        import asyncio
        log_guardia("🧠 [HILO] Iniciando asyncio.run()...")
        asyncio.run(IRIS.run())
    except Exception as e:
        log_guardia(f"🔥 ERROR FATAL EN EL HILO:\n{traceback.format_exc()}")
        ui.puente.senal_log.emit(f"SYS Error Fatal")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    
    app = QApplication.instance() or QApplication(sys.argv)
    
    socket = QLocalSocket()
    socket.connectToServer("IRIS_SingleInstance")
    if socket.waitForConnected(500):
        print("SYS: Ya hay una instancia de I.R.I.S. en ejecución. Cerrando clon.")
        sys.exit(1)
        
    local_server = QLocalServer()
    local_server.listen("IRIS_SingleInstance")
    
    if os.path.exists("guardia_log.txt"):
        try:
            os.remove("guardia_log.txt") 
        except PermissionError:
            pass 
            
    log_guardia("=======================================")
    log_guardia("🛡️ INICIANDO ARRANQUE DEL SISTEMA IRIS")
    log_guardia("=======================================")
    
    load_dotenv()
    if not os.getenv("GEMINI_API_KEY"):
        log_guardia("❌ Error: No se encontró GEMINI_API_KEY en el archivo .env")
        sys.exit(1)
        
    SetLogLevel(-1)
    auto_descubrir_herramientas()
            
    ventana = IRISUI() 
    ventana._win.show() 
    
    hilo_ia = threading.Thread(target=iniciar_cerebro, args=(ventana,), daemon=True)
    hilo_ia.start()
    
    sys.exit(app.exec())