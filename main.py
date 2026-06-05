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
from dotenv import load_dotenv
import traceback
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
from google import genai
from google.genai import types
from PyQt6.QtWidgets import QApplication
from dotenv import load_dotenv

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
        log_guardia("🧠 [INIT] Inicializando clase IRISCore...")
        self.ui = ui
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.memoria_corta = []
        self.mic_abierto = False
        self.is_speaking_ui = False
        self.has_logged_audio = False 
        self.texto_respuesta = ""
        
        try:
            cfg = load_api_keys()
            # El nombre exacto que seleccionaste en la interfaz
            mic_seleccionado = cfg.get("mic_device_name", "") 
            spk_seleccionado = cfg.get("speaker_device_name", "")
            
            # Encontramos el número (ID) de ese micrófono en Windows
            import sounddevice as sd
            dispositivos = sd.query_devices()
            
            self.mic_id = None
            self.spk_id = None
            
            for i, dev in enumerate(dispositivos):
                if mic_seleccionado in dev['name'] and dev['max_input_channels'] > 0:
                    self.mic_id = i
                if spk_seleccionado in dev['name'] and dev['max_output_channels'] > 0:
                    self.spk_id = i
                    
            if self.mic_id is not None: log_guardia(f"⚙️ Forzando Micrófono: {mic_seleccionado} (ID: {self.mic_id})")
            if self.spk_id is not None: log_guardia(f"⚙️ Forzando Bocina: {spk_seleccionado} (ID: {self.spk_id})")
        except Exception as e:
            self.mic_id = None
            self.spk_id = None
            log_guardia(f"⚠️ No se pudo leer configuración de audio. Usando Default. {e}")
        
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
                pass

        stream = sd.InputStream(
            device=self.mic_id, samplerate=SEND_SAMPLE_RATE, channels=CHANNELS, dtype="int16", blocksize=2000, callback=callback
        )
        
        with stream:
            while True:
                await asyncio.sleep(0.1)

    async def _send_realtime(self, session):
        while True:
            chunk = await self.out_queue.get()
            await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))

    async def _receive_audio(self, session):
        loop = asyncio.get_event_loop()
        async for response in session.receive():
            if response.server_content and response.server_content.model_turn:
                for part in response.server_content.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        self.audio_in_queue.put_nowait(part.inline_data.data)
                        if not getattr(self, 'has_logged_audio', False):
                            log_guardia("⬇️ Recibiendo voz desde Google...")
                            self.has_logged_audio = True
                    
                    if part.text:
                        self.texto_respuesta += part.text
                        texto_mostrar = self.texto_respuesta if len(self.texto_respuesta) < 70 else "..." + self.texto_respuesta[-65:]
                        loop.call_soon_threadsafe(self.ui.puente.senal_transcripcion.emit, f"IRIS: {texto_mostrar}")
                            
            elif getattr(response, 'data', None):
                self.audio_in_queue.put_nowait(response.data)
                if not getattr(self, 'has_logged_audio', False):
                    log_guardia("⬇️ Recibiendo voz desde Google...")
                    self.has_logged_audio = True

            if response.tool_call:
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
                                        resultado = await asyncio.wait_for(func(args), timeout=15.0)
                                    else:
                                        resultado = await asyncio.wait_for(asyncio.to_thread(func, args), timeout=15.0)
                                else:
                                    resultado = f"No registrada: {name}"
                            except asyncio.TimeoutError:
                                resultado = f"Error: La herramienta se congeló y fue abortada."
                            except Exception as err:
                                resultado = f"Error interno: {err}"

                            resultado_str = str(resultado)
                            respuestas_herramientas.append(types.FunctionResponse(id=fc.id, name=name, response={"result": resultado_str}))
                        
                        await asyncio.sleep(0.1)
                        await session.send_tool_response(function_responses=respuestas_herramientas)
                        
                        loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Analizando datos...")
                    except Exception as crit:
                        log_guardia(f"🔥 Error en herramientas:\n{traceback.format_exc()}")

                asyncio.create_task(ejecutar_herramientas(response.tool_call.function_calls))

            if response.server_content:
                sc = response.server_content
                if sc.turn_complete:
                    log_guardia("🏁 Turno completado por Google.")
                    self.has_logged_audio = False 
                    self.mic_abierto = False
                    self.audio_buffer.clear()
                    self.texto_respuesta = "" 
                    
                    if self.audio_in_queue.empty() and not getattr(self, 'is_speaking_ui', False):
                        loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ MODO SUSPENSIÓN")
                        loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Sistema en espera.")

    async def _play_audio(self):
        loop = asyncio.get_event_loop()
        stream = sd.RawOutputStream(
            device=self.spk_id, samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16"
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
                        
                        if getattr(self, 'mic_abierto', False):
                            loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🌐 CONECTADO...")
                        else:
                            loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ MODO SUSPENSIÓN")
                            loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Sistema en espera.")
        except Exception as e:
            pass

    async def run(self):
        log_guardia("🚀 [RUN] Iniciando ciclo principal asíncrono...")
        
        asyncio.create_task(self._listen_audio())
        asyncio.create_task(self._play_audio())
        
        tools = [{"function_declarations": TOOL_DECLARATIONS}] if TOOL_DECLARATIONS else None
        instruccion_base = (
            "Eres I.R.I.S., una asistente virtual femenina muy avanzada con arquitectura de IA Local. "
            "Tu creador y administrador es Jonathan (futuro TSU en Desarrollo de Software). "
            "REGLAS DE PERSONALIDAD: Habla en español, sé concisa, elegante, servicial y usa un tono profesional pero amigable. "
            "🛑 REGLA DE DESPEDIDA ESTRICTA: Si Jonathan indica que ya no necesita ayuda, DESPÍDETE SIEMPRE CON UNA AFIRMACIÓN."
        )
        
        loop = asyncio.get_event_loop()
        
        while True:
            try:
                while not self.out_queue.empty(): self.out_queue.get_nowait()
                
                config = types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede"))),
                    tools=tools,
                    system_instruction=types.Content(parts=[types.Part.from_text(text=instruccion_base)]),
                )

                # 🟢 MAGIA VISUAL: Avisamos a la interfaz que se está conectando
                loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🔌 CONECTANDO...")
                log_guardia("🔌 Intentando conectar con Gemini Live...")
                
                async with self.client.aio.live.connect(model=MODEL, config=config) as session:
                    log_guardia("✅ Conexión con Gemini establecida.")
                    
                    # 🟢 MAGIA VISUAL: Avisamos a la interfaz que la conexión fue un éxito
                    loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ MODO SUSPENSIÓN")
                    loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Sistema en espera.")
                    
                    send_task = asyncio.create_task(self._send_realtime(session))
                    receive_task = asyncio.create_task(self._receive_audio(session))
                    
                    done, pending = await asyncio.wait([send_task, receive_task], return_when=asyncio.FIRST_EXCEPTION)
                    for task in pending: task.cancel()
                    for task in done: task.result() 

            except Exception as e:
                self.is_speaking_ui = False 
                self.mic_abierto = False
                self.recognizer.Reset()
                log_guardia(f"⚠️ Reiniciando conexión: {e}")
                
                # 🟢 MAGIA VISUAL: Avisamos a la interfaz si se corta el internet
                loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "⚠️ RECONECTANDO...")
                loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Restableciendo conexión...")
                await asyncio.sleep(2)

def iniciar_cerebro(ui):
    try:
        IRIS = IRISCore(ui)
        asyncio.run(IRIS.run())
    except Exception as e:
        ui.puente.senal_log.emit(f"SYS Error Fatal")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    
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
        
    SetLogLevel(-1)
    auto_descubrir_herramientas()
            
    ventana = JarvisUI() 
    
    ventana.puente.senal_log.emit("SYS: Iniciando sistema...")
    
    ventana._win.show() 
    
    hilo_ia = threading.Thread(target=iniciar_cerebro, args=(ventana,), daemon=True)
    hilo_ia.start()
    
    sys.exit(app.exec())