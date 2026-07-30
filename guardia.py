import sys
import os
import socket
import time
import queue
import json
import subprocess

# 🚀 RENDIMIENTO: los .pyc van FUERA de OneDrive. El proyecto vive en una carpeta
# sincronizada y cada __pycache__ regenerado disparaba una subida de OneDrive
# (CPU + disco). Se fija ANTES de importar los módulos pesados, y main.py lo
# hereda por la variable de entorno.
os.environ.setdefault("PYTHONPYCACHEPREFIX",
                      os.path.join(os.environ.get("LOCALAPPDATA", "."), "IRIS", "pycache"))
sys.pycache_prefix = os.environ["PYTHONPYCACHEPREFIX"]

import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
import keyboard

import audio_devices
from config_manager import load_api_keys

# 🔒 CANDADO DE INSTANCIA ÚNICA: se llegaron a acumular DOS guardias a la vez
# (cada arranque.bat sumaba uno), cada uno con su Vosk y su stream de micrófono:
# doble CPU y lag. El que no consigue el puerto se retira en silencio.
_CANDADO = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    _CANDADO.bind(("127.0.0.1", 47823))
    _CANDADO.listen(1)
except OSError:
    print("Ya hay otro guardián corriendo. Este se retira.")
    sys.exit(0)


def ui_viva():
    """¿Hay un main.py vivo? Se detecta por su tubería 'IRIS_SingleInstance'.

    Cubre el caso en que la UI se reinició sola (reinicio educado del núcleo):
    el main.py nuevo ya no es hijo nuestro, y sin este chequeo el guardián le
    pelearía el micrófono decodificando voz en paralelo.
    """
    try:
        return "IRIS_SingleInstance" in os.listdir(r"\\.\pipe")
    except Exception:
        return False

# --- SISTEMA DE LOGS INVISIBLE ---
# Se abre en modo "a": main.py también escribe en este archivo, y en modo "w"
# nuestras líneas caían encima de las suyas y borraban su diagnóstico.
RUTA_LOG = "guardia_log.txt"
try:
    if os.path.exists(RUTA_LOG) and os.path.getsize(RUTA_LOG) > 1_000_000:
        open(RUTA_LOG, "w", encoding="utf-8").close()
except Exception:
    pass

log_file = open(RUTA_LOG, "a", encoding="utf-8", buffering=1)
sys.stdout = log_file
sys.stderr = log_file

print(f"\n──────── nueva sesión [{time.strftime('%d/%m %H:%M:%S')}] ────────")
print(f"[{time.strftime('%H:%M:%S')}] Iniciando sistema de vigilancia silencioso...")

SetLogLevel(-1)

jarvis_en_pantalla = False
audio_queue = queue.Queue()


def lanzar_jarvis():
    global jarvis_en_pantalla

    # Si ya está en pantalla, ignoramos cualquier intento de duplicar la UI
    if jarvis_en_pantalla:
        return

    jarvis_en_pantalla = True
    print("🚀 Lanzando UI Principal de JARVIS...")

    # Lanzamiento controlado de la interfaz
    try:
        subprocess.run([sys.executable, "main.py"])
    except Exception as e:
        print(f"❌ Error al ejecutar main.py: {e}")

    print("💤 UI cerrada por el usuario. Retomando guardia en 1 segundo...")
    time.sleep(1)

    # Limpiamos la cola de audio acumulada para evitar falsos disparos al regresar
    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            break

    jarvis_en_pantalla = False


def vigilar():
    global jarvis_en_pantalla
    try:
        model = Model("vosk_model")
        print("✔️ Modelo Vosk cargado correctamente.")
    except Exception as e:
        print(f"❌ Error crítico cargando Vosk: {e}")
        sys.exit(1)

    recognizer = KaldiRecognizer(model, 16000)

    # 🎤 El MISMO micrófono que usará main.py (antes abríamos el "por defecto" de
    # Windows, que puede ser un micrófono virtual mudo aunque abra sin error).
    cfg = load_api_keys()
    mic_idx, mic_nombre, mic_aviso = audio_devices.elegir_microfono(cfg.get("mic_device_name", ""))
    print(f"🎤 Micrófonos detectados: {audio_devices.describir_entradas()}")
    print(f"🎤 Escuchando por: [{mic_idx}] {mic_nombre}")
    if mic_aviso:
        print(f"⚠️ {mic_aviso}")

    def callback(indata, frames, time_info, status):
        # Solo encolamos audio si la UI no está abierta en pantalla
        if not jarvis_en_pantalla:
            audio_queue.put(bytes(indata))

    # Asignamos el atajo global usando una función lambda segura
    keyboard.add_hotkey('ctrl+shift+j', lambda: lanzar_jarvis())
    print("⌨️ Atajo global activado: Ctrl + Shift + J")

    ALIAS_JARVIS = {"iris", "yris", "iriz", "yriz", "ivis", "jarvis"}

    ZEROS = None  # bloque de silencio digital puro (para saltarse a Vosk)

    while True:
        # 🟢 Mientras la UI está en pantalla (nuestra o reiniciada por su cuenta)
        # el micrófono es SUYO: esperamos sin tocarlo.
        if jarvis_en_pantalla or ui_viva():
            time.sleep(0.5)
            continue

        print("🛡️ Guardia en posición. Esperando voz o teclado...")
        despertar = False
        bloques_mudos = 0
        aviso_silencio = False
        chequeo_ui = 0

        try:
            # El stream se abre y se cierra limpiamente en cada ciclo de escucha activa
            with sd.RawInputStream(device=mic_idx, samplerate=16000, blocksize=4000,
                                   dtype='int16', channels=1, callback=callback):
                while not despertar and not jarvis_en_pantalla:
                    # Cada ~2s comprobamos si apareció una UI que no lanzamos
                    # nosotros: si vive, le cedemos el micrófono de inmediato.
                    chequeo_ui += 1
                    if chequeo_ui >= 4:
                        chequeo_ui = 0
                        if ui_viva():
                            break
                    try:
                        # Timeout corto para revisar frecuentemente si la UI se activó por teclado
                        data = audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue

                    # 🚀 Silencio digital absoluto (micrófono muerto o virtual mudo):
                    # no hay nada que reconocer, Vosk no gasta CPU en ceros.
                    if ZEROS is None or len(ZEROS) != len(data):
                        ZEROS = b"\x00" * len(data)
                    es_cero = (data == ZEROS)

                    # 🔇 Vigilante de silencio digital: si el micrófono no entrega
                    # NADA durante medio minuto, lo decimos en vez de fingir que
                    # vigilamos (esto delata micrófonos virtuales apagados).
                    if not aviso_silencio:
                        if es_cero:
                            bloques_mudos += 1
                            if bloques_mudos >= 120:  # ~30 s de ceros absolutos
                                aviso_silencio = True
                                print(f"🔇 El micrófono '{mic_nombre}' lleva 30s entregando silencio absoluto. "
                                      "No podré oír el wake-word: revisa que sea el micrófono correcto en Ajustes.")
                        else:
                            bloques_mudos = 0

                    if es_cero:
                        continue  # nada que reconocer: Vosk no gasta CPU en ceros

                    if recognizer.AcceptWaveform(data):
                        resultado = json.loads(recognizer.Result())
                        texto = resultado.get("text", "").lower()
                    else:
                        # Resultados parciales: despertamos en cuanto suena el nombre,
                        # sin esperar a que Vosk cierre la frase completa.
                        resultado = json.loads(recognizer.PartialResult())
                        texto = resultado.get("partial", "").lower()

                    palabras = set(texto.replace(",", " ").replace(".", " ").split())

                    if ALIAS_JARVIS.intersection(palabras) and not jarvis_en_pantalla:
                        print(f"✨ ¡Despertar por voz detectado a las {time.strftime('%H:%M:%S')}! ('{texto}')")
                        recognizer.Reset()
                        despertar = True
        except Exception as e:
            print(f"⚠️ No pude abrir el micrófono [{mic_idx}] {mic_nombre}: {e}")
            print("   Reintentando en 3 segundos...")
            time.sleep(3)
            continue

        # Si salimos del bloque "with", el micrófono se libera temporalmente
        if despertar and not jarvis_en_pantalla:
            lanzar_jarvis()


if __name__ == "__main__":
    vigilar()
