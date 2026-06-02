import asyncio
import json
import queue
import sys
import threading
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
from google import genai
from google.genai import types
from PyQt6.QtWidgets import QApplication
import os
import ctypes

from actions.open_app import open_app
from actions.computer_control import computer_control
from actions.screen_vision import screen_vision
from actions.system_monitor import system_monitor
from actions.auto_programmer import auto_programmer
from actions.tirar_dado import tirar_dado
from actions.abrir_warframe import abrir_warframe
from actions.web_search import web_search
from ui import JarvisUI
from dotenv import load_dotenv


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

# --- CATÁLOGO DE HERRAMIENTAS ---
TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": "Abre un programa o aplicación en la computadora.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {"type": "STRING", "description": "Nombre de la app"}
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "computer_control",
        "description": "Controla el teclado físico de la PC.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "type | press | hotkey"},
                "text": {"type": "STRING", "description": "El texto a escribir"},
                "keys": {"type": "STRING", "description": "Tecla a presionar o atajo"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "screen_vision",
        "description": "JARVIS puede VER la pantalla del usuario.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "describe | question | help",
                },
                "question": {
                    "type": "STRING",
                    "description": "Pregunta sobre la pantalla.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "system_monitor",
        "description": "Lee los sensores físicos de la computadora (CPU, RAM, Disco).",
        "parameters": {
            "type": "OBJECT",
            "properties": {"action": {"type": "STRING", "description": "check_system"}},
            "required": ["action"],
        },
    },
    {
        "name": "auto_programmer",
        "description": "Permite a JARVIS escribir su propio código Python para crear nuevas herramientas. Úsalo cuando el usuario te pida que programes una nueva habilidad, que crees una herramienta o que aprendas a hacer algo nuevo.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "Descripción de lo que debe hacer el código (ej: 'una herramienta para tirar un dado de 6 caras')"},
                "tool_name": {"type": "STRING", "description": "Nombre de la función en formato snake_case (ej: 'tirar_dado')"}
            },
            "required": ["request", "tool_name"]
        }
    },
    {
        "name": "tirar_dado",
        "description": "Lanza un dado virtual de 6 caras y devuelve el resultado. Úsalo cuando el usuario pida tirar un dado o probar su suerte.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "lanzar"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "abrir_warframe",
        "description": "Abre el juego Warframe directamente en la cuenta del usuario. Úsalo cuando el usuario quiera jugar Warframe y no quiera pasar por el launcher.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "abrir_warframe"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "web_search",
        "description": "Realiza una búsqueda en la web y devuelve un resumen de los resultados. Úsalo cuando el usuario te pida buscar algo en internet o necesite información actualizada.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "La consulta de búsqueda que quieres realizar."}
            },
            "required": ["query"]
        }
    }
]


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
        self.despierto = False

    async def _listen_audio(self):
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            if self.despierto:
                loop.call_soon_threadsafe(self.out_queue.put_nowait, indata.tobytes())

        stream = sd.InputStream(
            samplerate=SEND_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=8000, 
            callback=callback,
        )
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
        async for response in session.receive():
            
            # 1. Extraer el audio y las transcripciones
            server_content = response.server_content
            if server_content is not None:
                model_turn = server_content.model_turn
                if model_turn is not None:
                    for part in model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            self.audio_in_queue.put_nowait(part.inline_data.data)
                
                if server_content.output_transcription and server_content.output_transcription.text:
                    texto = server_content.output_transcription.text.strip()
                    if texto:
                        self.ui.puente.senal_transcripcion.emit(texto)

            # 2. Manejar llamadas a las Herramientas
            if response.tool_call:
                async def ejecutar_herramientas(llamadas):
                    respuestas_herramientas = []
                    for fc in llamadas:
                        name = fc.name
                        args = dict(fc.args) if fc.args else {}
                        self.ui.puente.senal_log.emit(f"⚙️ JARVIS ejecutando: {name}")

                        resultado = "Herramienta desconocida."
                        try:
                            if name == "open_app":
                                resultado = await asyncio.to_thread(open_app, args)
                            elif name == "computer_control":
                                resultado = await asyncio.to_thread(computer_control, args)
                            elif name == "screen_vision":
                                resultado = await asyncio.to_thread(screen_vision, args)
                            elif name == "system_monitor":
                                resultado = await asyncio.to_thread(system_monitor, args)
                            elif name == "auto_programmer":
                                resultado = await asyncio.to_thread(auto_programmer, args)
                            elif name == "tirar_dado":
                                resultado = await asyncio.to_thread(tirar_dado, args)
                            elif name == "abrir_warframe":
                                resultado = await asyncio.to_thread(abrir_warframe, args)
                            elif name == "web_search":
                                resultado = await asyncio.to_thread(web_search, args)
                        except Exception as e:
                            resultado = f"Error: {e}"

                        respuestas_herramientas.append(
                            types.FunctionResponse(
                                id=fc.id, name=name, response={"result": str(resultado)}
                            )
                        )
                    
                    # 🟢 RESTAURADO: Tu método original para herramientas
                    await session.send_tool_response(
                        function_responses=respuestas_herramientas
                    )

                asyncio.create_task(
                    ejecutar_herramientas(response.tool_call.function_calls)
                )

            if response.server_content:
                sc = response.server_content
                if sc.output_transcription and sc.output_transcription.text:
                    texto = sc.output_transcription.text.strip()
                    if texto:
                        # Emitimos la transcripción de forma segura para que se escriba horizontal
                        self.ui.puente.senal_transcripcion.emit(texto)

    async def _play_audio(self):
        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16"
        )
        stream.start()
        while True:
            chunk = await self.audio_in_queue.get()
            await asyncio.to_thread(stream.write, chunk)

    async def run(self):
        # 1. Convertimos tu catálogo viejo al formato estricto del nuevo SDK
        lista_funciones = []
        for t in TOOL_DECLARATIONS:
            lista_funciones.append(
                types.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters=t["parameters"] # El SDK lo convierte a esquema automáticamente
                )
            )
        
        # 2. Creamos la configuración de conexión blindada
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            tools=[types.Tool(function_declarations=lista_funciones)],
            system_instruction=types.Content(
                parts=[
                    types.Part.from_text(
                        text="Eres J.A.R.V.I.S., un asistente virtual. "
                        "Tu creador es Jonathan. "
                        "REGLAS: Habla en español, sé conciso y usa un tono estilo Iron Man."
                    )
                ]
            ),
        )

        while True:
            try:
                self.ui.puente.senal_estado.emit("🔌 CONECTANDO...")
                async with self.client.aio.live.connect(
                    model=MODEL, config=config
                ) as session:
                    self.ui.puente.senal_estado.emit("🟢 EN LÍNEA")
                    self.ui.puente.senal_log.emit(
                        "SYS: Conexión establecida. JARVIS escuchando."
                    )
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._listen_audio())
                        tg.create_task(self._send_realtime(session))
                        tg.create_task(self._receive_audio(session))
                        tg.create_task(self._play_audio())
            except Exception as e:
                import traceback
                print("\n🚨 DETALLE DEL ERROR CRÍTICO AL DESCUBIERTO:")
                traceback.print_exc()
                
                self.ui.puente.senal_estado.emit("⚠️ RECONECTANDO...")
                self.ui.puente.senal_log.emit(
                    "SYS: Conexión perdida. Reconectando en 2s..."
                )
                await asyncio.sleep(1)


def iniciar_cerebro(ui):
    jarvis = JarvisCore(ui)
    try:
        import asyncio
        asyncio.run(jarvis.run())
    except Exception as e:
        ui.puente.senal_log.emit(f"SYS Error Fatal: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 1. Instanciamos la interfaz
    ventana = JarvisUI() 
    
    # 2. En lugar de ventana.show(), llamamos a la ventana interna que creamos:
    ventana._win.show() 
    
    # El hilo de IA sigue igual
    hilo_ia = threading.Thread(target=iniciar_cerebro, args=(ventana,), daemon=True)
    hilo_ia.start()
    
    sys.exit(app.exec())
