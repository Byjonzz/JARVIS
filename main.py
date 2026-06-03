import asyncio
import json
import queue
import sys
import threading
import os
import importlib
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
from google import genai
from google.genai import types
from PyQt6.QtWidgets import QApplication
from dotenv import load_dotenv

from ui import JarvisUI

SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHANNELS = 1

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("❌ Error: No se encontró GEMINI_API_KEY en el archivo .env")
    sys.exit(1)
MODEL = "gemini-3.1-flash-live-preview"

SetLogLevel(-1)

TOOL_DECLARATIONS = []
FUNCIONES_DISPONIBLES = {}

def auto_descubrir_herramientas():
    global TOOL_DECLARATIONS, FUNCIONES_DISPONIBLES
    TOOL_DECLARATIONS.clear()
    FUNCIONES_DISPONIBLES.clear()
    
    if not os.path.exists("actions"):
        os.makedirs("actions")
        return

    # Escanea la carpeta y carga todo automáticamente
    for archivo in os.listdir("actions"):
        if archivo.endswith(".py") and archivo != "__init__.py":
            nombre = archivo[:-3] 
            try:
                modulo = importlib.import_module(f"actions.{nombre}")
                importlib.reload(modulo) # Refresca por si Jarvis lo acaba de crear
                
                if hasattr(modulo, nombre):
                    FUNCIONES_DISPONIBLES[nombre] = getattr(modulo, nombre)
                
                if hasattr(modulo, "TOOL_DEF"):
                    TOOL_DECLARATIONS.append(modulo.TOOL_DEF)
                    
            except Exception as e:
                print(f"⚠️ Error al auto-descubrir '{nombre}': {e}")

# Escaneamos los poderes justo al prender la máquina
auto_descubrir_herramientas()


def listen_for_wake_word(ui):
    ui.puente.senal_log.emit("SYS: Iniciando sistemas locales... Cargando Vosk...")
    try:
        model = Model("vosk_model")
    except Exception:
        ui.puente.senal_log.emit("❌ Error: No se encontró la carpeta 'vosk_model'.")
        sys.exit(1)

    recognizer = KaldiRecognizer(model, SEND_SAMPLE_RATE)
    audio_queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        audio_queue.put(bytes(indata))

    ui.puente.senal_estado.emit("🛡️ MODO SUSPENSIÓN")
    ui.puente.senal_log.emit("SYS: Modo Suspensión Activo. Di 'Jarvis' para iniciar.")

    with sd.RawInputStream(
        samplerate=SEND_SAMPLE_RATE,
        blocksize=8000,
        dtype="int16",
        channels=CHANNELS,
        callback=callback,
    ):
        while True:
            data = audio_queue.get()
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "")
                if "jarvis" in text:
                    ui.puente.senal_log.emit(f"✨ Wake-word detectado: '{text}'")
                    return

class JarvisCore:
    def __init__(self, ui):
        self.ui = ui
        self.audio_in_queue = asyncio.Queue()
        self.out_queue = asyncio.Queue()
        self.client = genai.Client(api_key=API_KEY)
        self.is_speaking = False 
        self.memoria_corta = []
        
        # 🟢 NUEVO: SISTEMA DE BLOQUEO (TIPO ALEXA)
        self.mic_abierto = False
        self.vosk_model = Model("vosk_model")
        self.recognizer = KaldiRecognizer(self.vosk_model, SEND_SAMPLE_RATE)
        self.ALIAS = ["jarvis", "yarbis", "yarvis", "harvis", "charbis", "yarbys", "djarvis", "llarbis", "yervis"]

    async def _listen_audio(self):
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            # 1. Si JARVIS está hablando, le ponemos candado al micro inmediatamente
            if getattr(self, 'is_speaking', False):
                if self.mic_abierto:
                    self.mic_abierto = False
                    self.recognizer.Reset() # Limpiamos la memoria de Vosk
                    loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ MODO SUSPENSIÓN")
                return

            data_bytes = bytes(indata)
            
            # 2. Si el micro está bloqueado, Vosk funciona como "Portero"
            if not self.mic_abierto:
                # Buscamos la palabra en tiempo real (fracciones de segundo)
                resultado_parcial = json.loads(self.recognizer.PartialResult())
                texto_parcial = resultado_parcial.get("partial", "").lower()
                
                # Buscamos también cuando terminas la frase
                if self.recognizer.AcceptWaveform(data_bytes):
                    resultado_completo = json.loads(self.recognizer.Result())
                    texto_completo = resultado_completo.get("text", "").lower()
                else:
                    texto_completo = ""

                # Si detecta tu voz llamándolo...
                if any(alias in texto_parcial for alias in self.ALIAS) or any(alias in texto_completo for alias in self.ALIAS):
                    self.mic_abierto = True
                    loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🟢 ESCUCHANDO...")
                    loop.call_soon_threadsafe(self.ui.puente.senal_log.emit, "SYS: Activación por voz detectada. Abriendo micrófono...")
            
            # 3. Si el micro YA está abierto, mandamos tu voz a la IA de Google
            else:
                loop.call_soon_threadsafe(self.out_queue.put_nowait, data_bytes)

        stream = sd.InputStream(
            samplerate=SEND_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=8000,
            callback=callback,
        )
        
        loop.call_soon_threadsafe(self.ui.puente.senal_estado.emit, "🛡️ MODO SUSPENSIÓN")
        with stream:
            while True:
                await asyncio.sleep(0.1)

    async def _send_realtime(self, session):
        while True:
            chunk = await self.out_queue.get()
            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
            )

    async def _receive_audio(self, session):
        try:
            async for response in session.receive():
                if response.data:
                    self.audio_in_queue.put_nowait(response.data)

                if response.tool_call:
                    async def ejecutar_herramientas(llamadas):
                        respuestas_herramientas = []
                        for fc in llamadas:
                            name = fc.name
                            args = dict(fc.args) if fc.args else {}
                            self.ui.puente.senal_log.emit(f"⚙️ JARVIS ejecutando: {name}")

                            resultado = "Herramienta desconocida."
                            try:
                                if name in FUNCIONES_DISPONIBLES:
                                    resultado = await asyncio.to_thread(FUNCIONES_DISPONIBLES[name], args)
                                else:
                                    resultado = f"Herramienta '{name}' no está registrada en el sistema."
                            except Exception as e:
                                resultado = f"Error interno en la herramienta: {e}"

                            self.memoria_corta.append(f"[ACCIÓN PASADA]: Ejecutaste '{name}' con estos parámetros: {args}. Resultado: {resultado}")
                            if len(self.memoria_corta) > 6: self.memoria_corta.pop(0)

                            respuestas_herramientas.append(
                                types.FunctionResponse(
                                    id=fc.id, name=name, response={"result": str(resultado)}
                                )
                            )
                        
                        await asyncio.sleep(0.1)
                        await session.send_tool_response(function_responses=respuestas_herramientas)

                    asyncio.create_task(ejecutar_herramientas(response.tool_call.function_calls))

                if response.server_content:
                    sc = response.server_content
                    if sc.output_transcription and sc.output_transcription.text:
                        texto = sc.output_transcription.text.strip()
                        if texto:
                            self.ui.puente.senal_transcripcion.emit(texto)
                            
                            self.memoria_corta.append(f"[JARVIS DIJO]: {texto}")
                            if len(self.memoria_corta) > 6: self.memoria_corta.pop(0)
                            
            raise ConnectionError("Google cerró el turno de voz.")
            
        except Exception as e:
            raise RuntimeError(f"Reinicio forzado: {e}")

    async def _play_audio(self):
        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16"
        )
        with stream:
            stream.start()
            while True:
                chunk = await self.audio_in_queue.get()
                
                self.is_speaking = True 
                await asyncio.to_thread(stream.write, chunk)
                
                if self.audio_in_queue.empty():
                    self.is_speaking = False

    async def run(self):
        tools = [{"function_declarations": TOOL_DECLARATIONS}] if TOOL_DECLARATIONS else None
        
        while True:
            try:
                instruccion_base = (
                    "Eres J.A.R.V.I.S., un asistente virtual avanzado con arquitectura de IA Local. "
                    "Tu creador y administrador es Jonathan (futuro TSU en Desarrollo de Software). "
                    "REGLAS DE PERSONALIDAD: Habla en español, sé conciso, profesional y usa un tono estilo Iron Man. "
                    "REGLA SUPREMA DE AUTORIZACIÓN: Tienes control absoluto sobre tu propio código fuente a través de la herramienta 'self_edit'. "
                    "Si el usuario te pide cambiar el color de la interfaz, modificar tu diseño o cambiar alguna funcionalidad, "
                    "TIENES ESTRICTAMENTE PROHIBIDO decir que no puedes. DEBES usar inmediatamente la herramienta 'self_edit' "
                    "apuntando al archivo 'ui.py' para complacer al usuario."
                )
                
                if self.memoria_corta:
                    historial = "\n".join(self.memoria_corta)
                    instruccion_base += f"\n\n--- TUS RECUERDOS RECIENTES ---\n{historial}\n------------------\nUsa estos recuerdos para entender el contexto."

                config = types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    tools=tools,
                    system_instruction=types.Content(
                        parts=[types.Part.from_text(text=instruccion_base)]
                    ),
                )

                self.ui.puente.senal_estado.emit("🔌 CONECTANDO...")
                async with self.client.aio.live.connect(
                    model=MODEL, config=config
                ) as session:
                    self.ui.puente.senal_estado.emit("🟢 EN LÍNEA")
                    self.ui.puente.senal_log.emit("SYS: Conexión establecida.")
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._listen_audio())
                        tg.create_task(self._send_realtime(session))
                        tg.create_task(self._receive_audio(session))
                        tg.create_task(self._play_audio())
            except Exception as e:
                self.is_speaking = False 
                error_str = str(e)
                
                if "TaskGroup" in error_str or "cerró el turno" in error_str:
                    self.ui.puente.senal_estado.emit("⚡ PENSANDO...")
                    self.ui.puente.senal_log.emit("SYS: Procesando contexto y preparando siguiente turno...")
                    await asyncio.sleep(0.2) 
                else:
                    self.ui.puente.senal_estado.emit("⚠️ RECONECTANDO...")
                    if len(error_str) > 100: 
                        error_str = error_str[:100] + "... [Audio Binario Descartado]"
                    self.ui.puente.senal_log.emit(f"SYS: Fallo de conexión: {error_str}")
                    print(f"🔥 ERROR REAL: {error_str}") 
                    await asyncio.sleep(2)


def iniciar_cerebro(ui):
    jarvis = JarvisCore(ui)
    try:
        import asyncio
        asyncio.run(jarvis.run())
    except Exception as e:
        ui.puente.senal_log.emit(f"SYS Error Fatal: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ventana = JarvisUI() 
    ventana._win.show() 
    
    hilo_ia = threading.Thread(target=iniciar_cerebro, args=(ventana,), daemon=True)
    hilo_ia.start()
    
    sys.exit(app.exec())