"""
Diagnostico del wake-word de I.R.I.S.

Replica EXACTAMENTE lo que hace el callback de main.py (mismo dispositivo, mismo
tamano de bloque, mismo reconocedor Vosk, mismo recorte biometrico) pero imprimiendo
todo lo que main.py se calla, para saber en que eslabon se rompe la cadena:

    microfono -> nivel de senal -> Vosk transcribe "iris" -> guardian de voz aprueba

Uso:  .venv\\Scripts\\python.exe diagnostico_voz.py
Sin emojis a proposito: la consola de Windows los rompe al redirigir la salida.
"""
import collections
import json
import sys
import time

import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel

import audio_devices
from config_manager import load_api_keys
from actions import voice_guard

SR = 16000
BLOQUE = 4000          # mismo blocksize que main.py
SEGUNDOS = 10
WAKE_WORDS = {"iris", "yris", "iriz", "yriz", "jarvis"}


def barra(valor, maximo, ancho=30):
    n = int(min(1.0, valor / maximo) * ancho)
    return "#" * n + "." * (ancho - n)


def main():
    print("=" * 72)
    print("DIAGNOSTICO DEL WAKE-WORD DE I.R.I.S.")
    print("=" * 72)

    cfg = load_api_keys()
    idx, nombre, aviso = audio_devices.elegir_microfono(cfg.get("mic_device_name", ""))
    print(f"\n[1/5] MICROFONO")
    print(f"      config : {cfg.get('mic_device_name', '')!r}")
    print(f"      elegido: [{idx}] {nombre}")
    if aviso:
        print(f"      AVISO  : {aviso}")

    print(f"\n[2/5] GUARDIAN DE VOZ")
    hay = voice_guard.hay_perfil()
    print(f"      voice_lock configurado : {cfg.get('voice_lock')}")
    print(f"      huella de voz grabada  : {hay}")
    print(f"      lock_activo()          : {voice_guard.lock_activo()}"
          "   <- si es True, el wake-word DEBE pasar la biometria")
    if hay:
        perfil = voice_guard._cargar()
        rig = int(cfg.get("voice_strictness", 50))
        umbral = voice_guard._umbral_efectivo(perfil)
        print(f"      umbral_base={perfil['umbral_base']:.3f}  rigidez={rig}"
              f"  -> UMBRAL A SUPERAR = {umbral:.3f}")

    SetLogLevel(-1)
    modelo = Model("vosk_model")
    rec = KaldiRecognizer(modelo, SR)

    print(f"\n[3/5] GRABANDO {SEGUNDOS} SEGUNDOS")
    print('      DI "IRIS" CLARO, 3 O 4 VECES, con pausas de un segundo entre cada una.')
    for c in (3, 2, 1):
        print(f"      empieza en {c}...", end="\r")
        time.sleep(1)
    print("      GRABANDO... habla ahora.                      ")

    audio = sd.rec(int(SEGUNDOS * SR), samplerate=SR, channels=1, dtype="int16", device=idx)
    sd.wait()
    audio = audio.reshape(-1)
    print("      listo.\n")

    print("[4/5] ANALISIS BLOQUE A BLOQUE (como el callback de main.py)")
    print("      bloque  nivel                          rms    VAD    transcripcion Vosk")
    buffer_audio = collections.deque(maxlen=15)
    ruido = None
    parciales = []
    finales = []
    detecciones = []
    pico_global = 0
    voz_activa_alguna = False

    n_bloques = len(audio) // BLOQUE
    for b in range(n_bloques):
        bloque = audio[b * BLOQUE:(b + 1) * BLOQUE]
        datos = bytes(bloque)
        buffer_audio.append(datos)

        pico = int(np.max(np.abs(bloque.astype(np.int32))))
        pico_global = max(pico_global, pico)
        rms = float(np.sqrt(np.mean(bloque.astype(np.float64) ** 2)))

        # Mismo detector de actividad de voz que main.py (piso acotado al arrancar,
        # suelo minimo derivado de mic_sensitivity, y correccion a la baja del piso)
        if ruido is None:
            ruido = float(np.clip(rms, 1.0, 150.0))
        try:
            sens = float(cfg.get("mic_sensitivity", 50))
        except Exception:
            sens = 50.0
        vad_min = max(60.0, 500.0 - 4.0 * min(max(sens, 0.0), 100.0))
        umbral_vad = max(ruido * 3.5, vad_min)
        voz_activa = rms > umbral_vad
        if not voz_activa:
            ruido = 0.95 * ruido + 0.05 * max(rms, 1.0)
        elif rms < ruido:
            ruido = max(rms, 1.0)
        else:
            voz_activa_alguna = True

        if rec.AcceptWaveform(datos):
            texto = json.loads(rec.Result()).get("text", "").lower()
            tipo = "FINAL"
            if texto:
                finales.append(texto)
        else:
            texto = json.loads(rec.PartialResult()).get("partial", "").lower()
            tipo = "parc."
            if texto and (not parciales or parciales[-1] != texto):
                parciales.append(texto)

        palabras = set(texto.replace(",", "").replace(".", "").split())
        golpe = WAKE_WORDS.intersection(palabras)

        marca = "SI " if voz_activa else "no "
        print(f"      {b:>4}   {barra(pico, 8000)} {rms:7.1f}  {marca}  [{tipo}] {texto[:40]}")

        if golpe and not detecciones:
            # Mismo recorte biometrico que main.py: los ultimos 6 bloques (~1.5 s)
            recorte = b"".join(list(buffer_audio)[-6:])
            ok, sim, seg = voice_guard.verificar_bytes(recorte)
            detecciones.append((b, sorted(golpe), ok, sim, seg))
            print(f"      >>> WAKE-WORD DETECTADO en el bloque {b}: {sorted(golpe)}")

    print(f"\n[5/5] VEREDICTO")
    print(f"      pico maximo de la grabacion: {pico_global} / 32768"
          f"  ({100.0 * pico_global / 32768:.1f}% de la escala)")
    if pico_global < 500:
        print("      [X] NIVEL DEMASIADO BAJO. Vosk no puede reconocer nada asi.")
        print("          Sube el volumen del microfono en Windows (Configuracion > Sonido >")
        print("          Entrada > tu microfono > Volumen) o acerca el brazo del microfono.")
    elif pico_global < 3000:
        print("      [!] Nivel bajo pero utilizable. Si Vosk falla, sube el volumen en Windows.")
    else:
        print("      [OK] Nivel de senal correcto.")

    print(f"      el detector de voz (VAD) se activo en algun bloque: {voz_activa_alguna}")
    if not voz_activa_alguna:
        print("          [X] Ningun bloque supero el umbral del detector de voz.")
        print("              La ventana de seguimiento no podria reabrir el microfono:")
        print("              sube mic_sensitivity en jarvis_config.json (100 = suelo minimo 100).")

    print(f"\n      transcripciones finales de Vosk: {finales if finales else '(ninguna)'}")
    print(f"      ultimos parciales vistos: {parciales[-6:] if parciales else '(ninguno)'}")

    if not detecciones:
        print("\n      [X] VOSK NUNCA TRANSCRIBIO UNA PALABRA DE LA LISTA:")
        print(f"          {sorted(WAKE_WORDS)}")
        print("          Mira arriba que escribio en su lugar: si sale algo parecido")
        print('          ("iri", "irix", "isis"...), el arreglo es anadir ese alias.')
    else:
        for b, golpe, ok, sim, seg in detecciones:
            print(f"\n      [OK] Vosk SI reconocio {golpe} en el bloque {b}.")
            print(f"      GUARDIAN DE VOZ sobre el recorte de 1.5 s:")
            print(f"          resultado = {ok}   (True=eres tu, False=otra voz, None=evidencia corta)")
            print(f"          similitud = {sim:.3f}   segundos de voz en el recorte = {seg:.2f}")
            if voice_guard.lock_activo():
                perfil = voice_guard._cargar()
                umbral = voice_guard._umbral_efectivo(perfil)
                if ok is False:
                    print(f"          [X] AQUI SE ROMPE: {sim:.3f} < {umbral:.3f}, el guardian te")
                    print("              rechaza y main.py ignora el wake-word en silencio.")
                    print("              Arreglo: baja la rigidez, vuelve a grabar la huella con")
                    print("              este microfono, o desactiva el guardian.")
                elif ok is None:
                    print("          [!] Evidencia insuficiente en el recorte. En modo flexible")
                    print("              (rigidez < 85) main.py ABRE el microfono igualmente.")
                else:
                    print("          [OK] El guardian te aprueba. El wake-word deberia abrir el microfono.")

        # Prueba extra: la grabacion completa deberia dar la mejor similitud posible
        ok_t, sim_t, seg_t = voice_guard.verificar_bytes(bytes(audio))
        print(f"\n      Referencia con los {SEGUNDOS} s completos: resultado={ok_t}"
              f" similitud={sim_t:.3f} voz={seg_t:.2f}s")
        print("      (si con 10 s tampoco te aprueba, la huella grabada no sirve para este microfono)")

    print("\n" + "=" * 72)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
