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
audio_queue = queue.Queue()

def lanzar_jarvis():
    global jarvis_en_pantalla
    
    # Si ya está en pantalla, ignoramos cualquier intento de duplicar la UI
    if jarvis_en_pantalla:
        return
        
    jarvis_en_pantalla = True
    print("🚀 Lanzando UI Principal de JARVIS...")
    sys.stdout.flush()
    
    # Lanzamiento controlado de la interfaz
    try:
        subprocess.run([sys.executable, "main.py"])
    except Exception as e:
        print(f"❌ Error al ejecutar main.py: {e}")
        sys.stdout.flush()
    
    print("💤 UI cerrada por el usuario. Retomando guardia en 1 segundo...")
    sys.stdout.flush()
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
        sys.stdout.flush()
        sys.exit(1)
        
    recognizer = KaldiRecognizer(model, 16000)

    def callback(indata, frames, time_info, status):
        # Solo encolamos audio si la UI no está abierta en pantalla
        if not jarvis_en_pantalla:
            audio_queue.put(bytes(indata))

    # Asignamos el atajo global usando una función lambda segura
    keyboard.add_hotkey('ctrl+shift+j', lambda: lanzar_jarvis())
    print("⌨️ Atajo global activado: Ctrl + Shift + J")
    sys.stdout.flush()

    ALIAS_JARVIS = ["iris, ivis,"]

    while True:
        print("🛡️ Guardia en posición. Esperando voz o teclado...")
        sys.stdout.flush() 
        
        # El stream se abre y se cierra limpiamente en cada ciclo de escucha activa
        with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype='int16', channels=1, callback=callback):
            despertar = False
            while not despertar and not jarvis_en_pantalla:
                try:
                    # Timeout corto para revisar frecuentemente si la UI se activó por teclado
                    data = audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if recognizer.AcceptWaveform(data):
                    resultado = json.loads(recognizer.Result())
                    texto = resultado.get("text", "").lower()
                    
                    if any(alias in texto for alias in ALIAS_JARVIS) and not jarvis_en_pantalla:
                        print(f"✨ ¡Despertar por voz detectado a las {time.strftime('%H:%M:%S')}!")
                        sys.stdout.flush()
                        despertar = True

        # Si salimos del bloque "with", el micrófono se libera temporalmente
        if despertar and not jarvis_en_pantalla:
            lanzar_jarvis()

if __name__ == "__main__":
    vigilar()