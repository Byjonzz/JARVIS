import sys
import os
import time
import queue
import json
import subprocess
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
import keyboard

# --- SISTEMA DE LOGS INVISIBLE ---
log_file = open("guardia_log.txt", "w", encoding="utf-8")
sys.stdout = log_file
sys.stderr = log_file

print(f"[{time.strftime('%H:%M:%S')}] Iniciando sistema de vigilancia silencioso...")
sys.stdout.flush()

SetLogLevel(-1)

jarvis_en_pantalla = False

def lanzar_jarvis():
    global jarvis_en_pantalla
    
    # Si el candado está puesto (la interfaz ya existe), ignoramos el doble teclazo
    if jarvis_en_pantalla:
        return
        
    # Ponemos el candado
    jarvis_en_pantalla = True
    print("🚀 Lanzando UI Principal de JARVIS...")
    sys.stdout.flush()
    
    # Lanzamiento de la interfaz
    subprocess.run([sys.executable, "main.py"])
    
    # Cuando la interfaz se cierra, el código llega aquí
    print("💤 UI cerrada por el usuario. Retomando guardia en 1 segundo...")
    sys.stdout.flush()
    time.sleep(1)
    
    # Quitamos el candado para el futuro
    jarvis_en_pantalla = False

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

    # 🟢 Asignamos el atajo global
    keyboard.add_hotkey('ctrl+shift+j', lanzar_jarvis)
    print("⌨️ Atajo global activado: Ctrl + Shift + J")
    sys.stdout.flush()

    # Red fonética para entender "Jarvis" con cualquier acento
    ALIAS_JARVIS = ["jarvis", "yarbis", "yarvis", "harvis", "charbis", "yarbys", "djarvis", "llarbis", "yervis"]

    while True:
        print("🛡️ Guardia en posición. Esperando voz o teclado...")
        sys.stdout.flush() 
        
        with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16', channels=1, callback=callback):
            despertar = False
            while not despertar:
                data = audio_queue.get()
                if recognizer.AcceptWaveform(data):
                    resultado = json.loads(recognizer.Result())
                    texto = resultado.get("text", "").lower()
                    
                    # 🟢 Solo despertamos por voz si no hay candado puesto
                    if any(alias in texto for alias in ALIAS_JARVIS) and not jarvis_en_pantalla:
                        print(f"✨ ¡Despertar por voz detectado a las {time.strftime('%H:%M:%S')}!")
                        sys.stdout.flush()
                        despertar = True

        if despertar:
            lanzar_jarvis()