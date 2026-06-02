import sys
import os
import time

# Todas las formas en las que Vosk podría interpretar "JARVIS"
ALIAS_JARVIS = [
    "jarvis",
    "yarbis",
    "yarvis",
    "harvis",
    "charbis",
    "yarbys",
    "djarvis",
    "llarbis",
    "yervis"
]

# --- SISTEMA DE LOGS INVISIBLE ---
# Evita que Python explote por no tener una consola donde hacer "print()"
log_file = open("guardia_log.txt", "w", encoding="utf-8")
sys.stdout = log_file
sys.stderr = log_file

print(f"[{time.strftime('%H:%M:%S')}] Iniciando sistema de vigilancia silencioso...")
sys.stdout.flush() # Obliga a guardar el texto inmediatamente en el .txt

import queue
import json
import subprocess
import keyboard
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)

def lanzar_jarvis():
    print("🚀 Lanzando UI Principal de JARVIS...")
    sys.stdout.flush()
    CREATE_NO_WINDOW = 0x08000000
    subprocess.run(["python", "main.py"], creationflags=CREATE_NO_WINDOW)
    print("💤 UI cerrada por el usuario. Retomando guardia...")
    sys.stdout.flush()
    time.sleep(1)

def vigilar():
    try:
        model = Model("vosk_model")
        print("✔️ Modelo Vosk cargado correctamente.")
    except Exception as e:
        print(f"❌ Error crítico cargando Vosk: {e}")
        sys.stdout.flush()
        sys.exit(1)
        
    recognizer = KaldiRecognizer(model, 16000)
    audio_queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        audio_queue.put(bytes(indata))
        
    keyboard.add_hotkey('ctrl+alt+j', lanzar_jarvis)
    print("⌨️ Atajo global activado: Ctrl + Alt + J")
    sys.stdout.flush()

    while True:
        print("🛡️ Guardia en posición. Esperando la palabra 'Jarvis' o el atajo de teclado...")
        sys.stdout.flush() 
        
        with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16', channels=1, callback=callback):
            despertar = False
            while not despertar:
                data = audio_queue.get()
                if recognizer.AcceptWaveform(data):
                    resultado = json.loads(recognizer.Result())
                    texto = resultado.get("text", "")
                    # Usamos la validación fonética que platicamos
                    if any(alias in texto for alias in ["jarvis", "yarbis", "harvis"]):
                        print("✨ ¡Despertar por voz detectado!")
                        sys.stdout.flush()
                        despertar = True

        # Lanzar la UI si se detectó la voz
        lanzar_jarvis()

        # --- MICRÓFONO LIBERADO ---
        print("🚀 Lanzando UI Principal de JARVIS...")
        sys.stdout.flush()

        CREATE_NO_WINDOW = 0x08000000
        subprocess.run(["python", "main.py"], creationflags=CREATE_NO_WINDOW)
        
        # Cuando el usuario hace clic en la X de la ventana, el código sigue aquí:
        print("💤 UI cerrada por el usuario. Retomando guardia en 1 segundos...")
        sys.stdout.flush()
        time.sleep(1)

if __name__ == "__main__":
    try:
        vigilar()
    except KeyboardInterrupt:
        print("🛑 Guardia apagado por interrupción.")
        sys.stdout.flush()
        sys.exit(0)