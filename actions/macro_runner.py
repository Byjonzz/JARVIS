import time

try:
    import pyautogui
except ImportError:
    pyautogui = None

def macro_runner(parameters: dict) -> str:
    macro_name = parameters.get("macro_name", "").lower()
    
    if not pyautogui:
        return "Error: Se necesita la librería 'pyautogui' para ejecutar macros."
        
    try:
        # Pequeña pausa para que el usuario suelte el teclado antes de que JARVIS tome el control
        time.sleep(0.5)
        
        if "guardar" in macro_name or "save" in macro_name:
            pyautogui.hotkey('ctrl', 's')
            return "Macro ejecutada: Documento guardado (Ctrl+S)."
            
        elif "copiar" in macro_name or "copy" in macro_name:
            pyautogui.hotkey('ctrl', 'c')
            return "Macro ejecutada: Texto copiado al portapapeles (Ctrl+C)."
            
        elif "pegar" in macro_name or "paste" in macro_name:
            pyautogui.hotkey('ctrl', 'v')
            return "Macro ejecutada: Texto pegado (Ctrl+V)."
            
        elif "formatear" in macro_name or "format" in macro_name:
            # Atajo clásico de VS Code para formatear código (Shift+Alt+F)
            pyautogui.hotkey('shift', 'alt', 'f')
            return "Macro ejecutada: Código formateado."
            
        elif "cerrar todo" in macro_name or "close_all" in macro_name:
            # Atajo para cerrar todas las pestañas de una app
            pyautogui.hotkey('ctrl', 'shift', 'w')
            return "Macro ejecutada: Cerrar todas las pestañas."

        else:
            return f"La macro '{macro_name}' no está configurada en mi sistema."
            
    except Exception as e:
        return f"Error ejecutando la macro: {e}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "macro_runner",
    "description": "Ejecuta atajos de teclado o macros en la computadora del usuario (guardar, copiar, pegar, formatear código). Úsalo cuando el usuario pida aplicar un atajo de teclado a lo que está haciendo actualmente.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "macro_name": {"type": "STRING", "description": "El nombre de la acción (ej: 'guardar', 'formatear código', 'copiar')."}
        },
        "required": ["macro_name"]
    }
}