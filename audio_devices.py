"""
🎤 audio_devices — Elección de micrófono y bocina compartida por guardia.py y main.py.

Antes cada uno elegía por su cuenta: el guardia abría el dispositivo "por defecto"
de Windows y main.py buscaba el nombre de los Ajustes. Si el defecto de Windows es
un micrófono VIRTUAL (Voicemod, Steam Streaming, NVIDIA Broadcast...) y su aplicación
no está enrutando la voz, el dispositivo existe y se abre sin error, pero entrega
silencio digital: Vosk nunca oye el wake-word y Gemini nunca oye una orden.

Aquí centralizamos la decisión y avisamos cuando el dispositivo elegido es sospechoso.
"""
import re

import sounddevice as sd

# Dispositivos que existen pero pueden entregar silencio si su app no está activa,
# o que no son un micrófono de voz real (mezcladores del sistema).
PALABRAS_VIRTUALES = (
    "VOICEMOD", "STEAM STREAMING", "VB-AUDIO", "VB-CABLE", "CABLE OUTPUT",
    "VIRTUAL", "DUMMY", "NVIDIA BROADCAST", "OBS ", "VOICEMEETER",
    "ASIGNADOR", "SOUND MAPPER", "PRIMARY SOUND",
)

# Entradas que capturan audio del sistema o de una línea auxiliar, no tu voz.
PALABRAS_LINEA = (
    "LINE ", "LINE(", "LÍNEA", "LINEA", "AUX", "STEREO MIX", "MEZCLA EST",
    "WHAT U HEAR", "LOOPBACK", "DIGITAL AUDIO",
)


def _norm(texto):
    """Normaliza un nombre de dispositivo para comparar sin ruido.

    MME recorta los nombres a 31 caracteres y les mete un índice ("2- Astro A50"),
    así que quitamos signos y números sueltos: 'Headphones (2- Astro A50 Game)'
    y 'Headphones (Astro A50 Game)' pasan a ser el mismo texto.
    """
    t = re.sub(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ ]+", " ", (texto or "").upper())
    return " ".join(p for p in t.split() if not p.isdigit())


def _contiene(nombre, palabras):
    n = nombre.upper()
    return any(p in n for p in palabras)


def es_virtual(nombre):
    return _contiene(nombre, PALABRAS_VIRTUALES)


def es_linea(nombre):
    return _contiene(nombre, PALABRAS_LINEA)


def _es_mme(dispositivo):
    try:
        return "MME" in sd.query_hostapis(dispositivo["hostapi"])["name"]
    except Exception:
        return False


def _listar(es_entrada):
    """Dispositivos MME con canales útiles, como (indice, dispositivo)."""
    clave = "max_input_channels" if es_entrada else "max_output_channels"
    salida = []
    for i, d in enumerate(sd.query_devices()):
        if d[clave] > 0 and _es_mme(d):
            salida.append((i, d))
    return salida


def _buscar_configurado(dispositivos, nombre_cfg):
    if not nombre_cfg:
        return None
    objetivo = _norm(nombre_cfg)
    if not objetivo:
        return None
    for i, d in dispositivos:
        nombre = _norm(d["name"])
        if nombre and (objetivo in nombre or nombre in objetivo):
            return i, d
    return None


def _mejor(dispositivos, puntuar):
    """Devuelve (indice, dispositivo, puntos) del mejor candidato (empate → índice menor)."""
    mejor = None
    for i, d in dispositivos:
        puntos = puntuar(d["name"])
        if mejor is None or puntos > mejor[2]:
            mejor = (i, d, puntos)
    return mejor


def elegir_microfono(nombre_cfg=""):
    """(indice, nombre, aviso) del micrófono a usar.

    Prioridad: el elegido en Ajustes → micrófono físico de diadema → cualquier
    micrófono físico → lo que haya. 'aviso' explica el riesgo si el elegido es
    virtual o una entrada de línea ("" si todo está en orden).
    """
    dispositivos = _listar(es_entrada=True)
    if not dispositivos:
        return None, "", "No encontré ningún dispositivo de entrada MME en el sistema."

    elegido = _buscar_configurado(dispositivos, nombre_cfg)
    if elegido:
        i, d = elegido
        return i, d["name"], _aviso_entrada(d["name"], configurado=True)

    def puntuar(nombre):
        n = nombre.upper()
        if es_virtual(n) or es_linea(n):
            return -1
        puntos = 0
        if "ASTRO" in n:
            puntos += 8
        if "HEADSET" in n or "HEADPHONE" in n or "DIADEMA" in n:
            puntos += 4
        if "MICROPHONE" in n or "MICRÓFONO" in n or "MICROFONO" in n or " MIC" in n:
            puntos += 2
        if "ARRAY" in n or "REALTEK" in n:
            puntos += 1  # micrófono integrado: sirve, pero es la última opción decente
        return puntos

    i, d, puntos = _mejor(dispositivos, puntuar)
    if puntos < 0:
        # Solo quedan virtuales o entradas de línea: usamos el primero, avisando.
        i, d = dispositivos[0]
    return i, d["name"], _aviso_entrada(d["name"], configurado=False)


def _aviso_entrada(nombre, configurado):
    origen = "configurado en Ajustes" if configurado else "elegido automáticamente"
    if es_virtual(nombre):
        return (f"El micrófono {origen} ('{nombre}') es virtual o un mezclador del sistema. "
                "Si su aplicación (Voicemod, Steam, NVIDIA Broadcast...) no está enrutando tu voz, "
                "solo llegará silencio y no oiré nada. Elige el micrófono físico en Ajustes.")
    if es_linea(nombre):
        return (f"El micrófono {origen} ('{nombre}') es una entrada de línea (audio del sistema o del juego), "
                "no el micrófono de tu voz. Elige el micrófono físico en Ajustes.")
    return ""


def elegir_bocina(nombre_cfg=""):
    """(indice, nombre, aviso) de la salida de audio a usar."""
    dispositivos = _listar(es_entrada=False)
    if not dispositivos:
        return None, "", "No encontré ningún dispositivo de salida MME en el sistema."

    elegido = _buscar_configurado(dispositivos, nombre_cfg)
    if elegido:
        i, d = elegido
        aviso = ""
        if es_virtual(d["name"]):
            aviso = (f"La bocina configurada ('{d['name']}') es virtual: puede que no oigas mi voz. "
                     "Elige tus audífonos reales en Ajustes.")
        return i, d["name"], aviso

    def puntuar(nombre):
        n = nombre.upper()
        if es_virtual(n):
            return -1
        puntos = 0
        if "ASTRO" in n:
            puntos += 8
        if "GAME" in n:
            puntos += 4      # en el Astro A50, "Game" es la salida que suena en la diadema
        if "VOICE" in n:
            puntos -= 2      # canal de chat, no el principal
        if "HEADPHONE" in n or "HEADSET" in n:
            puntos += 3
        return puntos

    i, d, puntos = _mejor(dispositivos, puntuar)
    if puntos < 0:
        i, d = dispositivos[0]
    return i, d["name"], ""


def describir_entradas():
    """Texto legible con todos los micrófonos disponibles (para logs y diagnóstico)."""
    lineas = []
    for i, d in _listar(es_entrada=True):
        etiquetas = []
        if es_virtual(d["name"]):
            etiquetas.append("virtual")
        if es_linea(d["name"]):
            etiquetas.append("línea")
        extra = f" [{', '.join(etiquetas)}]" if etiquetas else ""
        lineas.append(f"[{i}] {d['name']}{extra}")
    return " | ".join(lineas) if lineas else "ninguno"
