from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import pygetwindow as gw

def os_control(args):
    action = args.get("action")
    
    try:
        if action == "set_volume":
            level = float(args.get("level", 0.5)) # Nivel de 0.0 a 1.0
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevelScalar(level, None)
            return f"Volumen maestro ajustado al {int(level * 100)}%"
            
        elif action == "minimize_all":
            windows = gw.getAllWindows()
            for win in windows:
                if win.title and win.isActive:
                    win.minimize()
            return "Todas las ventanas han sido minimizadas."
            
        return "Acción de sistema no reconocida."
    except Exception as e:
        return f"Error controlando el sistema: {e}"