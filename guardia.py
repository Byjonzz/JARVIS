import sys
import os
import time
import queue
import json
import subprocess
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
import keyboard

import audio_devices
from config_manager import load_api_keys

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

    while True:
        # 🟢 Mientras la UI está en pantalla el micrófono es SUYO: esperamos sin
        # tocarlo. (Antes reabríamos el stream en bucle cerrado miles de veces por
        # minuto, peleándole el micrófono a main.py y llenando el log de basura.)
        if jarvis_en_pantalla:
            time.sleep(0.3)
            continue

        print("🛡️ Guardia en posición. Esperando voz o teclado...")
        despertar = False
        bloques_mudos = 0
        aviso_silencio = False

        try:
            # El stream se abre y se cierra limpiamente en cada ciclo de escucha activa
            with sd.RawInputStream(device=mic_idx, samplerate=16000, blocksize=4000,
                                   dtype='int16', channels=1, callback=callback):
                while not despertar and not jarvis_en_pantalla:
                    try:
                        # Timeout corto para revisar frecuentemente si la UI se activó por teclado
                        data = audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue

                    # 🔇 Vigilante de silencio digital: si el micrófono no entrega
                    # NADA durante medio minuto, lo decimos en vez de fingir que
                    # vigilamos (esto delata micrófonos virtuales apagados).
                    if not aviso_silencio:
                        if max(data) == 0 and min(data) == 0:
                            bloques_mudos += 1
                            if bloques_mudos >= 120:  # ~30 s de ceros absolutos
                                aviso_silencio = True
                                print(f"🔇 El micrófono '{mic_nombre}' lleva 30s entregando silencio absoluto. "
                                      "No podré oír el wake-word: revisa que sea el micrófono correcto en Ajustes.")
                        else:
                            bloques_mudos = 0

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
