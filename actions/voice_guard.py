"""
🗝️ voice_guard — El Guardián de Voz de I.R.I.S.

Verificación de hablante 100% local (NumPy puro, sin frameworks): crea una
huella acústica del usuario (estadísticas MFCC + similitud coseno) y permite:

1. Que el wake-word solo funcione con TU voz (nadie más puede despertar a IRIS).
2. La "ventana de seguimiento": tras cada respuesta de IRIS puedes seguir
   hablando SIN decir 'Iris'; solo tu voz reabre el micrófono. Voces ajenas
   y el silencio la cierran solas.

Archivos que genera:
- config/voice_profile.npz → tu huella de voz (embeddings + umbral calibrado)
"""
import json
import threading
import time
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
RUTA_PERFIL = BASE_DIR / "config" / "voice_profile.npz"
RUTA_CONFIG = BASE_DIR / "jarvis_config.json"

SR = 16000
N_FFT = 512
N_MELS = 40
N_MFCC = 20
FRAME = 400   # 25 ms
HOP = 160     # 10 ms

_LOCK = threading.Lock()
_PERFIL = None           # caché del perfil cargado de disco
_PERFIL_LEIDO = False
_ENROLL_PENDIENTE = False

# Ajustes leídos de jarvis_config.json (se aplican al arrancar; la herramienta
# 'enable'/'disable' los cambia en vivo y los persiste)
_AJUSTES = {"voice_lock": True, "voice_strictness": 50, "follow_up_window": 12}
try:
    if RUTA_CONFIG.exists():
        _cfg = json.loads(RUTA_CONFIG.read_text(encoding="utf-8"))
        _AJUSTES["voice_lock"] = bool(_cfg.get("voice_lock", True))
        _AJUSTES["voice_strictness"] = int(_cfg.get("voice_strictness", 50))
        _AJUSTES["follow_up_window"] = float(_cfg.get("follow_up_window", 12))
except Exception:
    pass


# ---------- Extracción de características (MFCC en numpy puro) ----------

def _mel_filterbank():
    def hz2mel(f): return 2595.0 * np.log10(1.0 + f / 700.0)
    def mel2hz(m): return 700.0 * (10 ** (m / 2595.0) - 1.0)
    puntos = mel2hz(np.linspace(hz2mel(60.0), hz2mel(7600.0), N_MELS + 2))
    bins = np.floor((N_FFT + 1) * puntos / SR).astype(int)
    fb = np.zeros((N_MELS, N_FFT // 2 + 1))
    for i in range(N_MELS):
        a, b, c = bins[i], bins[i + 1], bins[i + 2]
        if b <= a: b = a + 1
        if c <= b: c = b + 1
        fb[i, a:b] = (np.arange(a, b) - a) / (b - a)
        fb[i, b:c] = (c - np.arange(b, c)) / (c - b)
    return fb


def _dct_matrix():
    # DCT-II ortonormal, descartando el coeficiente 0 (volumen absoluto)
    k = np.arange(1, N_MFCC + 1)[:, None]
    n = (np.arange(N_MELS) + 0.5)[None, :]
    return np.cos(np.pi / N_MELS * k * n) * np.sqrt(2.0 / N_MELS)


_FB = _mel_filterbank()
_DCT = _dct_matrix()
_VENTANA_HAMMING = np.hamming(FRAME)


def _mfcc(x):
    """x: audio float64 en [-1, 1]. Devuelve (mfcc [T x 20], log-energía [T])."""
    if len(x) < FRAME + HOP:
        return None, None
    pre = np.empty_like(x)
    pre[0] = x[0]
    pre[1:] = x[1:] - 0.97 * x[:-1]
    idx = np.arange(0, len(pre) - FRAME + 1, HOP)
    tramas = np.stack([pre[i:i + FRAME] for i in idx]) * _VENTANA_HAMMING
    espectro = np.abs(np.fft.rfft(tramas, N_FFT)) ** 2
    mel = np.log(espectro @ _FB.T + 1e-8)
    mf = mel @ _DCT.T
    energia = np.log(np.sum(espectro, axis=1) + 1e-8)
    return mf, energia


# Log-energía espectral mínima de habla real (FFT sin normalizar: el ruido de
# fondo de un micrófono ronda -3..0.5 en esta escala; la voz supera 2.5)
UMBRAL_ENERGIA_ABS = 1.5

def _mascara_voz(energia):
    """Frames con voz. Criterio dual:
    - Clip mixto (voz + pausas): umbral relativo al rango de energías del clip.
    - Clip homogéneo (todo voz o todo silencio): umbral absoluto, porque el
      'piso' relativo sería la propia voz y la máscara saldría vacía."""
    piso = np.percentile(energia, 10)
    techo = np.percentile(energia, 95)
    if techo - piso < 3.0:
        return energia > UMBRAL_ENERGIA_ABS
    return energia > (piso + 0.35 * (techo - piso))


def _emb_de_frames(mf):
    """Embedding = [media, desviación, media-delta, desv-delta] normalizado L2."""
    if mf.shape[0] < 8:
        return None
    delta = mf[2:] - mf[:-2]
    v = np.concatenate([mf.mean(0), mf.std(0), delta.mean(0), delta.std(0)])
    norma = np.linalg.norm(v)
    return v / norma if norma > 0 else None


def _embedding(x_int16):
    """Devuelve (embedding, segundos_con_voz) de un clip int16."""
    x = x_int16.astype(np.float64) / 32768.0
    mf, energia = _mfcc(x)
    if mf is None:
        return None, 0.0
    voz = _mascara_voz(energia)
    seg_voz = float(voz.sum()) * HOP / SR
    if voz.sum() < 8:
        return None, seg_voz
    return _emb_de_frames(mf[voz]), seg_voz


# ---------- Perfil: crear, cargar, verificar ----------

def _cargar():
    global _PERFIL, _PERFIL_LEIDO
    if _PERFIL_LEIDO:
        return _PERFIL
    try:
        if RUTA_PERFIL.exists():
            datos = np.load(RUTA_PERFIL, allow_pickle=False)
            _PERFIL = {
                "chunks": datos["chunks"],
                "centroide": datos["centroide"],
                "umbral_base": float(datos["umbral_base"]),
                "seg_voz": float(datos["seg_voz"]),
            }
    except Exception:
        _PERFIL = None
    _PERFIL_LEIDO = True
    return _PERFIL


def hay_perfil() -> bool:
    with _LOCK:
        return _cargar() is not None


def lock_activo() -> bool:
    """El guardián actúa solo si está habilitado Y existe una huella grabada."""
    return bool(_AJUSTES.get("voice_lock", True)) and hay_perfil()


def modo_estricto() -> bool:
    """Con rigidez >= 85, hasta la evidencia insuficiente se rechaza."""
    return int(_AJUSTES.get("voice_strictness", 50)) >= 85


def ventana_segundos() -> float:
    try:
        return max(0.0, float(_AJUSTES.get("follow_up_window", 12)))
    except Exception:
        return 12.0


def _umbral_efectivo(perfil):
    base = perfil["umbral_base"]
    ajuste = (int(_AJUSTES.get("voice_strictness", 50)) - 50) / 50.0 * 0.07
    return float(np.clip(base + ajuste, 0.50, 0.97))


def crear_perfil(audio_bytes: bytes):
    """Construye la huella de voz desde ~30s de audio crudo int16 mono 16 kHz."""
    global _PERFIL, _PERFIL_LEIDO
    x = np.frombuffer(audio_bytes, dtype=np.int16)
    xf = x.astype(np.float64) / 32768.0
    mf, energia = _mfcc(xf)
    if mf is None:
        return False, "La grabación fue demasiado corta."

    voz = _mascara_voz(energia)
    seg_voz = float(voz.sum()) * HOP / SR
    if seg_voz < 8.0:
        return False, (f"Solo capté {seg_voz:.1f}s de voz clara (necesito al menos 8s). "
                       "Intenta de nuevo hablando más cerca del micrófono.")

    frames_voz = mf[voz]
    # Trozos de 2s (200 frames) con paso de 1s → varios embeddings de referencia
    chunks = []
    for ini in range(0, frames_voz.shape[0] - 200 + 1, 100):
        e = _emb_de_frames(frames_voz[ini:ini + 200])
        if e is not None:
            chunks.append(e)
    if len(chunks) < 4:
        return False, "No logré extraer suficientes muestras estables de tu voz. Intenta de nuevo."

    chunks = np.stack(chunks)
    centroide = chunks.mean(0)
    centroide /= np.linalg.norm(centroide)

    sims = chunks @ centroide
    umbral_base = float(np.clip(sims.mean() - 2.5 * sims.std() - 0.02, 0.55, 0.90))

    with _LOCK:
        RUTA_PERFIL.parent.mkdir(parents=True, exist_ok=True)
        np.savez(RUTA_PERFIL, chunks=chunks, centroide=centroide,
                 umbral_base=umbral_base, seg_voz=seg_voz)
        _PERFIL = {"chunks": chunks, "centroide": centroide,
                   "umbral_base": umbral_base, "seg_voz": seg_voz}
        _PERFIL_LEIDO = True

    return True, (f"Perfil de voz guardado: {seg_voz:.1f}s de voz, {len(chunks)} muestras, "
                  f"umbral calibrado {umbral_base:.2f}. Desde ahora solo tu voz me activa.")


def verificar_bytes(audio_bytes: bytes, min_seg=0.45):
    """Compara un clip contra la huella del usuario.

    Devuelve (resultado, similitud, segundos_de_voz):
    - True  → es la voz del usuario
    - False → es OTRA voz
    - None  → evidencia insuficiente (clip muy corto o sin perfil que comparar)
    """
    with _LOCK:
        perfil = _cargar()
    if perfil is None:
        return None, 0.0, 0.0
    try:
        x = np.frombuffer(audio_bytes, dtype=np.int16)
        emb, seg_voz = _embedding(x)
    except Exception:
        return None, 0.0, 0.0
    if emb is None or seg_voz < min_seg:
        return None, 0.0, seg_voz

    sim = 0.5 * float(perfil["centroide"] @ emb) + 0.5 * float(np.max(perfil["chunks"] @ emb))
    return (sim >= _umbral_efectivo(perfil)), sim, seg_voz


# ---------- Enrolamiento diferido (main.py lo consulta) ----------

import unicodedata as _ud

_FRASES_ENROLL = (
    "aprende mi voz", "aprender mi voz", "aprende tu mi voz",
    "graba mi voz", "grabar mi voz", "grava mi voz",
    "registra mi voz", "registrar mi voz",
    "memoriza mi voz", "memorizar mi voz",
    "aprende mi huella",
)
_FRASES_NEGACION = ("borra", "elimina", "quita", "desactiva", "olvida")


def frase_pide_enrolamiento(texto: str) -> bool:
    """Detecta en la transcripción del usuario una orden directa de grabar su voz.
    Red de seguridad para cuando el modelo 'promete' grabar pero no llama la herramienta."""
    if not texto:
        return False
    t = texto.lower()
    t = "".join(c for c in _ud.normalize("NFD", t) if _ud.category(c) != "Mn")
    if any(neg in t for neg in _FRASES_NEGACION):
        return False
    return any(frase in t for frase in _FRASES_ENROLL)


def solicitar_enrolamiento():
    global _ENROLL_PENDIENTE
    _ENROLL_PENDIENTE = True


def enroll_pendiente() -> bool:
    return _ENROLL_PENDIENTE


def consumir_enroll():
    global _ENROLL_PENDIENTE
    _ENROLL_PENDIENTE = False


# ---------- Persistencia del interruptor en jarvis_config.json ----------

def _persistir_ajuste(clave, valor):
    try:
        cfg = {}
        if RUTA_CONFIG.exists():
            cfg = json.loads(RUTA_CONFIG.read_text(encoding="utf-8"))
        cfg[clave] = valor
        RUTA_CONFIG.write_text(json.dumps(cfg, indent=4, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ---------- Herramienta expuesta a Gemini ----------

def voice_guard(parameters: dict) -> str:
    global _PERFIL, _PERFIL_LEIDO
    action = (parameters.get("action") or "status").lower()

    if action == "enroll":
        solicitar_enrolamiento()
        return ("Enrolamiento programado. Dile al usuario EXACTAMENTE esto y luego guarda silencio "
                "SIN hacer preguntas: en cuanto termines de hablar sonará un tono y grabaré su voz "
                "durante 30 segundos; que hable con naturalidad o lea cualquier texto en voz alta, "
                "y al finalizar una campana confirmará que su huella de voz quedó guardada.")

    elif action == "status":
        with _LOCK:
            perfil = _cargar()
        estado_lock = "ACTIVADO" if _AJUSTES.get("voice_lock", True) else "DESACTIVADO"
        if perfil is None:
            return (f"Guardián de voz {estado_lock}, pero AÚN NO HAY huella de voz grabada "
                    "(sin huella no puedo filtrar voces). Pide 'aprende mi voz' para grabarla.")
        return (f"Guardián de voz {estado_lock}. Huella grabada con {perfil['seg_voz']:.1f}s de voz "
                f"({len(perfil['chunks'])} muestras), umbral {perfil['umbral_base']:.2f}, "
                f"rigidez {_AJUSTES.get('voice_strictness', 50)}/100, ventana de seguimiento "
                f"{ventana_segundos():.0f}s.")

    elif action == "enable":
        _AJUSTES["voice_lock"] = True
        _persistir_ajuste("voice_lock", True)
        return "Guardián de voz ACTIVADO: solo la voz registrada del usuario podrá activarme."

    elif action == "disable":
        _AJUSTES["voice_lock"] = False
        _persistir_ajuste("voice_lock", False)
        return "Guardián de voz DESACTIVADO: volveré a responder al wake-word de cualquier voz."

    elif action == "delete":
        with _LOCK:
            try:
                if RUTA_PERFIL.exists():
                    RUTA_PERFIL.unlink()
                _PERFIL = None
                _PERFIL_LEIDO = True
            except Exception as e:
                return f"No pude borrar la huella: {e}"
        return "Huella de voz eliminada. Puedes grabar una nueva cuando quieras."

    return "Acción no reconocida. Usa 'enroll', 'status', 'enable', 'disable' o 'delete'."


# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "voice_guard",
    "description": (
        "Guardián biométrico de voz de I.R.I.S. Úsalo cuando el usuario pida que aprendas o "
        "reconozcas su voz ('aprende mi voz' → action 'enroll'), pregunte por el estado del "
        "guardián ('status'), quiera activarlo/desactivarlo ('enable'/'disable') o borrar su "
        "huella ('delete')."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "'enroll' (grabar la huella de voz del usuario), 'status', 'enable', 'disable' o 'delete'."}
        },
        "required": ["action"]
    }
}
