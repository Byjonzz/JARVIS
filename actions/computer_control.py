import os
import time

def computer_control(parameters: dict) -> str:
    action = parameters.get("action", "").lower()
    
    # 📸 CAPTURAS DE PANTALLA
    if action == "take_screenshot":
        try:
            import mss
            from PIL import Image
            
            save_dir = os.path.join(os.path.dirname(__file__), "..", "config")
            os.makedirs(save_dir, exist_ok=True)
            path = os.path.join(save_dir, f"screenshot_{int(time.time())}.png")
            
            with mss.mss() as sct:
                sct_img = sct.grab(sct.monitors[0])
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                img.save(path)
            
            return f"Captura de pantalla tomada y guardada en: {path}"
        except Exception as e:
            return f"Error tomando captura: {e}"
            
    # 🎵 CONTROL MULTIMEDIA
    if action == "media_control":
        sub_action = parameters.get("sub_action", "").lower()
        try:
            import pyautogui
            if sub_action in ["play_pause", "play", "pause"]:
                pyautogui.press('playpause')
                return "Reproducción/Pausa ejecutada."
            elif sub_action in ["next", "next_track"]:
                pyautogui.press('nexttrack')
                return "Siguiente pista ejecutada."
            elif sub_action in ["prev", "prev_track"]:
                pyautogui.press('prevtrack')
                return "Pista anterior ejecutada."
            elif sub_action == "mute":
                pyautogui.press('volumemute')
                return "Sonido silenciado/activado."
            elif sub_action == "volume_up":
                pyautogui.press('volumeup', presses=5)
                return "Volumen subido."
            elif sub_action == "volume_down":
                pyautogui.press('volumedown', presses=5)
                return "Volumen bajado."
            else:
                return f"Comando multimedia desconocido: {sub_action}"
        except Exception as e:
            return f"Error en control multimedia: {e}"

    # ⌨️ ESCRITURA FANTASMA
    if action == "type":
        text_to_type = parameters.get("text", "")
        if not text_to_type:
            return "Error: Falta el texto a escribir."
        try:
            import pyautogui
            time.sleep(0.5) 
            pyautogui.write(text_to_type, interval=0.01)
            return f"Texto escrito con éxito: '{text_to_type}'"
        except Exception as e:
            return f"Error escribiendo texto: {e}"
            
    # 🪟 CONTROL DE VENTANAS
    if action == "window_control":
        sub_action = parameters.get("sub_action", "").lower()
        target = parameters.get("target", "").lower()
        
        try:
            import pygetwindow as gw
            import pyautogui
            
            if target:
                windows = [w for w in gw.getAllWindows() if target in w.title.lower() and w.title.strip()]
            else:
                windows = [gw.getActiveWindow()]
                
            if not windows or not windows[0]:
                return f"No se encontró ninguna ventana con el nombre '{target}'."
                
            win = windows[0]
            
            if sub_action == "close_tab":
                win.activate()
                time.sleep(0.2)
                pyautogui.hotkey('ctrl', 'w')
                return f"Pestaña cerrada en {win.title}."
            elif sub_action == "close":
                win.close()
                return f"Ventana cerrada: {win.title}."
            elif sub_action == "minimize":
                win.minimize()
                return f"Ventana minimizada: {win.title}."
            elif sub_action == "maximize":
                if win.isMinimized: win.restore()
                win.maximize()
                win.activate()
                return f"Ventana maximizada: {win.title}."
        except Exception as e:
            return f"Error en control de ventanas: {e}"

    return f"Acción '{action}' no reconocida por el sistema de control."

# 🟢 EL MANUAL PARA QUE TU ARQUITECTURA LO ENCUENTRE Y CONECTE MAGÍCAMENTE
TOOL_DEF = {
    "name": "computer_control",
    "description": "Controla el hardware, teclado, volumen, multimedia y manipula las ventanas de la computadora del usuario.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING", 
                "description": "La acción principal a realizar. Puede ser: take_screenshot, media_control, type, window_control"
            },
            "sub_action": {
                "type": "STRING", 
                "description": "Sub-acción requerida. Para media_control: play_pause, next, prev, mute, volume_up, volume_down. Para window_control: close, minimize, maximize, close_tab"
            },
            "text": {
                "type": "STRING", 
                "description": "El texto que se debe simular que se escribe en el teclado (Solo si action es 'type')"
            },
            "target": {
                "type": "STRING", 
                "description": "El nombre de la aplicación o ventana a afectar (Solo si action es 'window_control')"
            }
        },
        "required": ["action"]
    }
}