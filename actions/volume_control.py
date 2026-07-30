"""
volume_control — Volumen maestro de Windows para I.R.I.S.

Generada por el auto-programador (nvidia/nemotron-3-ultra-550b-a55b) y revisada a
mano: el borrador original usaba wintypes.ULONG_PTR (no existe: el módulo no
cargaba), liberaba COM antes de usar la interfaz y declaraba minimum/maximum en el
esquema, campos que la API de Gemini rechaza.

Método principal: pycaw (control exacto). Respaldo: teclas multimedia del sistema.
"""
import ctypes

# Intentar pycaw; si falta, queda el respaldo de teclas multimedia
try:
    from comtypes import CoInitialize, CoUninitialize
    from pycaw.pycaw import AudioUtilities
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False

# Teclas multimedia (Virtual Key Codes)
VK_VOLUME_UP = 0xAF
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_MUTE = 0xAD
KEYEVENTF_KEYUP = 0x0002


def send_media_key(vk_code):
    """Pulsa una tecla multimedia del sistema (keybd_event: simple y fiable)."""
    user32 = ctypes.windll.user32
    user32.keybd_event(vk_code, 0, 0, 0)
    user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def volume_control(parameters: dict) -> str:
    """Controla el volumen maestro de Windows.

    parameters:
        action: 'up' | 'down' | 'set' | 'mute' | 'unmute'
        level:  0-100 (solo para 'set')
    """
    action = str(parameters.get("action", "")).lower().strip()
    level = parameters.get("level")

    valid_actions = ["up", "down", "set", "mute", "unmute"]
    if action not in valid_actions:
        return f"Error: Acción '{action}' no válida. Use: {', '.join(valid_actions)}"

    # --- MÉTODO 1: pycaw (preciso) ---
    if PYCAW_AVAILABLE:
        try:
            # COM se inicializa por hilo (main.py ejecuta herramientas en hilos) y
            # se libera SOLO al terminar de usar la interfaz.
            CoInitialize()
            try:
                # En esta versión de pycaw, GetSpeakers() devuelve un AudioDevice
                # cuya propiedad EndpointVolume ya activa la interfaz COM correcta.
                volume = AudioUtilities.GetSpeakers().EndpointVolume
                current_mute = volume.GetMute()
                current_level = volume.GetMasterVolumeLevelScalar()  # 0.0 a 1.0

                if action == "mute":
                    if not current_mute:
                        volume.SetMute(1, None)
                        return "Volumen silenciado."
                    return "El volumen ya estaba silenciado."

                if action == "unmute":
                    if current_mute:
                        volume.SetMute(0, None)
                        return "Volumen activado."
                    return "El volumen ya estaba activo."

                if action == "set":
                    if level is None:
                        return "Error: para 'set' necesito 'level' (0-100)."
                    try:
                        target = int(level)
                    except (TypeError, ValueError):
                        return "Error: 'level' debe ser un número entero de 0 a 100."
                    if not 0 <= target <= 100:
                        return "Error: 'level' debe estar entre 0 y 100."
                    volume.SetMasterVolumeLevelScalar(target / 100.0, None)
                    if current_mute:
                        volume.SetMute(0, None)
                    return f"Volumen establecido al {target}%."

                if action == "up":
                    nuevo = min(1.0, current_level + 0.05)
                elif action == "down":
                    nuevo = max(0.0, current_level - 0.05)
                volume.SetMasterVolumeLevelScalar(nuevo, None)
                if current_mute:
                    volume.SetMute(0, None)
                verbo = "subido" if action == "up" else "bajado"
                return f"Volumen {verbo} al {int(round(nuevo * 100))}%."
            finally:
                CoUninitialize()
        except Exception:
            pass  # cualquier fallo COM cae al respaldo de teclas multimedia

    # --- MÉTODO 2: Respaldo con teclas multimedia ---
    try:
        if action == "mute" or action == "unmute":
            send_media_key(VK_VOLUME_MUTE)
            return f"Comando '{action}' enviado con la tecla multimedia (alterna el silencio)."
        if action == "up":
            send_media_key(VK_VOLUME_UP)
            return "Volumen subido con la tecla multimedia."
        if action == "down":
            send_media_key(VK_VOLUME_DOWN)
            return "Volumen bajado con la tecla multimedia."
        return ("Error: 'set' (porcentaje exacto) necesita la librería 'pycaw'; "
                "con teclas multimedia solo puedo subir, bajar o silenciar.")
    except Exception as e:
        return f"Error crítico controlando el volumen: {e}"


# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "volume_control",
    "description": (
        "Controla el volumen maestro de Windows: subir ('up', +5%), bajar ('down', -5%), "
        "poner un porcentaje exacto ('set' con level 0-100), silenciar ('mute') y "
        "reactivar ('unmute'). Úsala siempre que el usuario hable del volumen del sistema."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["up", "down", "set", "mute", "unmute"],
                "description": "'up' (subir 5%), 'down' (bajar 5%), 'set' (porcentaje exacto), 'mute', 'unmute'."
            },
            "level": {
                "type": "INTEGER",
                "description": "Nivel objetivo de 0 a 100. Solo se usa con action='set'."
            }
        },
        "required": ["action"]
    }
}
