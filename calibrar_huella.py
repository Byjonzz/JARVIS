"""
Regraba y VALIDA la huella de voz de I.R.I.S.

El problema que arregla: la huella anterior se calibraba comparando el perfil consigo
mismo (siempre ~0.96) y el umbral acababa clavado en el techo de 0.90, asi que el
guardian rechazaba al propio usuario y no habia ajuste en la interfaz capaz de
compensarlo.

Como se valida aqui, que es lo importante: se graba una sola vez y el audio se PARTE.
La huella se construye con los primeros 25 s y se verifica contra los ultimos 10 s,
que el algoritmo no ha visto nunca. Si aprobara solo con el audio con el que se
entreno, la medicion no valdria nada.

Uso:  .venv\\Scripts\\python.exe calibrar_huella.py
Hace copia de seguridad de config/voice_profile.npz antes de tocar nada.
Sin emojis a proposito: la consola de Windows los rompe al redirigir la salida.
"""
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

import audio_devices
from config_manager import load_api_keys
from actions import voice_guard as vg

SR = 16000
SEG_ENTRENO = 25
SEG_PRUEBA = 10
SEG_TOTAL = SEG_ENTRENO + SEG_PRUEBA
RECORTE_SEG = 2.5          # lo que main.py manda al guardian al oir el wake-word

TEXTO_SUGERIDO = """
      Lee esto en voz alta, o habla de lo que quieras con naturalidad.
      Lo importante es hablar SEGUIDO, sin silencios largos, a tu volumen normal
      y a la distancia a la que le hablas siempre:

      "Iris, quiero que reconozcas mi voz. Voy a hablar de forma natural durante
       medio minuto para que aprendas como sueno. Hoy quiero revisar el correo,
       poner musica y saber que tiempo hace. Iris, abre el navegador. Iris, sube
       el volumen. Iris, cuentame algo interesante. Esta es mi voz normal,
       hablando como hablo siempre, sin forzar nada y sin gritar."
"""


def cuenta_atras(mensaje):
    for c in (3, 2, 1):
        print(f"      {mensaje} en {c}...", end="\r")
        time.sleep(1)
    print("      GRABANDO... habla ahora.                                   ")


def recortes(audio, seg, paso_seg):
    """Trocea el audio en recortes del tamano que usa main.py en marcha."""
    n = int(seg * SR)
    paso = int(paso_seg * SR)
    for ini in range(0, len(audio) - n + 1, paso):
        yield audio[ini:ini + n]


def main():
    print("=" * 74)
    print("REGRABAR Y VALIDAR LA HUELLA DE VOZ")
    print("=" * 74)

    cfg = load_api_keys()
    idx, nombre, aviso = audio_devices.elegir_microfono(cfg.get("mic_device_name", ""))
    print(f"\n[1/6] MICROFONO: [{idx}] {nombre}")
    if aviso:
        print(f"      AVISO: {aviso}")

    ruta = vg.RUTA_PERFIL
    if ruta.exists():
        copia = ruta.with_suffix(".npz.bak")
        shutil.copy2(ruta, copia)
        print(f"\n[2/6] COPIA DE SEGURIDAD de tu huella anterior en:\n      {copia}")
        print("      (si algo sale mal, renombrala a voice_profile.npz)")
    else:
        print("\n[2/6] No habia huella previa que respaldar.")

    print(f"\n[3/6] GRABANDO {SEG_TOTAL} SEGUNDOS DE VOZ CONTINUA")
    print(TEXTO_SUGERIDO)
    cuenta_atras("empieza")

    audio = sd.rec(int(SEG_TOTAL * SR), samplerate=SR, channels=1, dtype="int16", device=idx)
    for s in range(SEG_TOTAL):
        time.sleep(1)
        restante = SEG_TOTAL - s - 1
        etapa = "entrenamiento" if s < SEG_ENTRENO else "PRUEBA (voz nueva)"
        print(f"      {s + 1:>2}/{SEG_TOTAL}s  [{etapa}]  quedan {restante}s   ", end="\r")
    sd.wait()
    audio = audio.reshape(-1)
    print("\n      listo.")

    pico = int(np.max(np.abs(audio.astype(np.int32))))
    print(f"      pico de la grabacion: {pico}/32768 ({100.0 * pico / 32768:.1f}%)")
    if pico < 500:
        print("      [X] Nivel demasiado bajo para construir una huella fiable. Sube el")
        print("          volumen del microfono en Windows y vuelve a intentarlo.")
        return 1

    entreno = audio[:SEG_ENTRENO * SR]
    prueba = audio[SEG_ENTRENO * SR:]

    print(f"\n[4/6] CONSTRUYENDO LA HUELLA con los primeros {SEG_ENTRENO}s")
    ok, msg = vg.crear_perfil(bytes(entreno))
    print(f"      {'[OK]' if ok else '[X]'} {msg}")
    if not ok:
        print("      No se guardo nada nuevo; tu huella anterior sigue intacta.")
        return 1

    vg._PERFIL_LEIDO = False          # forzamos relectura desde disco
    perfil = vg._cargar()
    longs = perfil.get("longitudes")
    print(f"      version del perfil: {perfil.get('version')}")
    if longs is not None:
        for w in sorted(set(np.asarray(longs).tolist())):
            print(f"        muestras de {w * 10 / 1000:.1f}s de voz: {int((np.asarray(longs) == w).sum())}")
    umbral = vg._umbral_efectivo(perfil)
    print(f"      umbral_base calibrado: {perfil['umbral_base']:.3f}")
    print(f"      UMBRAL EFECTIVO (rigidez {cfg.get('voice_strictness', 50)}): {umbral:.3f}")

    print(f"\n[5/6] VALIDACION CIEGA con los ultimos {SEG_PRUEBA}s (voz que la huella NO vio)")
    print(f"      Cada recorte imita lo que main.py manda al guardian: {RECORTE_SEG}s.")
    print("      recorte    similitud   voz(s)   veredicto")
    sims, aceptados, indecisos, rechazados = [], 0, 0, 0
    for i, tr in enumerate(recortes(prueba, RECORTE_SEG, 1.0)):
        res, sim, seg = vg.verificar_bytes(bytes(tr))
        if res is True:
            v, aceptados = "ACEPTA", aceptados + 1
        elif res is False:
            v, rechazados = "RECHAZA", rechazados + 1
        else:
            v, indecisos = "(evidencia corta)", indecisos + 1
        if res is not None:
            sims.append(sim)
        print(f"      {i:>4}       {sim:.3f}      {seg:.2f}    {v}")

    print(f"\n[6/6] VEREDICTO")
    total = aceptados + rechazados
    if not total:
        print("      [X] Ningun recorte tenia voz suficiente. Habla mas seguido y reintenta.")
        return 1
    sims = np.array(sims)
    print(f"      recortes con voz: {total}   aceptados: {aceptados}   rechazados: {rechazados}"
          f"   sin evidencia: {indecisos}")
    print(f"      similitud sobre voz nueva -> min {sims.min():.3f}  media {sims.mean():.3f}  max {sims.max():.3f}")
    print(f"      umbral a superar: {umbral:.3f}   margen medio: {sims.mean() - umbral:+.3f}")

    tasa = 100.0 * aceptados / total
    print()
    if tasa >= 90:
        print(f"      [OK] Te reconoce en el {tasa:.0f}% de los recortes. La huella sirve.")
        print("           Ya puedes abrir I.R.I.S. y decir 'Iris'.")
    elif tasa >= 60:
        print(f"      [!] Te reconoce en el {tasa:.0f}% de los recortes: funcionara, pero a veces")
        print("          tendras que repetir. Baja voice_strictness en jarvis_config.json")
        print(f"          (cada 10 puntos menos bajan el umbral 0.03) o regraba mas cerca del microfono.")
    else:
        print(f"      [X] Solo te reconoce en el {tasa:.0f}% de los recortes. No confies en esta huella.")
        sugerido = max(0, int(cfg.get("voice_strictness", 50)) - int((umbral - sims.mean() + 0.05) / 0.003))
        print(f"          Opciones: poner voice_strictness cerca de {sugerido}, regrabar hablando")
        print("          mas seguido y cerca del microfono, o poner voice_lock=false y quedarte")
        print("          sin biometria (el wake-word volveria a funcionar para cualquier voz).")
        print(f"          Tu huella anterior sigue en {ruta.with_suffix('.npz.bak')}")

    print("\n      Nota: la red de seguridad de main.py abre el microfono igualmente tras 3")
    print("      rechazos seguidos, asi que no puedes quedarte encerrado fuera.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
