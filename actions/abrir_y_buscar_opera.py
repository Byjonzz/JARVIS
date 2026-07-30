import subprocess
import time
import sys
import platform
import shlex
import os
from typing import Dict, Any

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

def abrir_y_buscar_opera(parameters: Dict[str, Any]) -> str:
    """
    Abre el navegador Opera y realiza una búsqueda del término proporcionado.
    Utiliza subprocess para lanzar el navegador y pyautogui para la interacción de UI.
    """
    termino_busqueda = parameters.get("termino", "").strip()
    
    if not termino_busqueda:
        return "Error: El parámetro 'termino' es obligatorio y no puede estar vacío."

    if not PYAUTOGUI_AVAILABLE:
        return "Error crítico: La librería 'pyautogui' no está instalada. Ejecute 'pip install pyautogui'."

    # Configuración de seguridad de pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.5

    sistema = platform.system()
    opera_cmd = ""
    
    # Determinar comando de lanzamiento según SO
    if sistema == "Windows":
        # Intentar rutas comunes en Windows
        possible_paths = [
            r"C:\Program Files\Opera\launcher.exe",
            r"C:\Program Files (x86)\Opera\launcher.exe",
            r"C:\Users\{}\AppData\Local\Programs\Opera\launcher.exe".format(os.getenv('USERNAME', '')),
            "opera" # Si está en PATH
        ]
        found = False
        for path in possible_paths:
            expanded = os.path.expandvars(path)
            if os.path.exists(expanded) or path == "opera":
                opera_cmd = expanded
                found = True
                break
        if not found:
            return "Error: No se encontró el ejecutable de Opera en rutas estándar de Windows."

    elif sistema == "Darwin": # macOS
        opera_cmd = "open -a Opera"
    elif sistema == "Linux":
        opera_cmd = "opera"
    else:
        return f"Error: Sistema operativo no soportado: {sistema}"

    try:
        # 1. Lanzar Opera
        # Usamos shell=True en macOS para el comando 'open -a', en otros Popen con lista es mejor.
        if sistema == "Darwin":
            subprocess.Popen(opera_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            # En Windows/Linux pasar como lista si es ruta, o string si es comando PATH
            if isinstance(opera_cmd, str) and " " in opera_cmd and sistema == "Windows":
                 subprocess.Popen([opera_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                 subprocess.Popen(shlex.split(opera_cmd), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 2. Esperar a que la ventana aparezca y cargue (brute force wait)
        # Tiempo generoso para inicio en frío
        time.sleep(3.5) 

        # 3. Enfocar barra de direcciones y buscar
        # Atajo universal: Ctrl+L (Windows/Linux), Cmd+L (Mac)
        if sistema == "Darwin":
            pyautogui.hotkey('command', 'l')
        else:
            pyautogui.hotkey('ctrl', 'l')
        
        time.sleep(0.3)
        
        # Escribir término de búsqueda (Opera usa el motor de búsqueda predeterminado en la barra de dir)
        pyautogui.write(termino_busqueda, interval=0.01)
        time.sleep(0.2)
        pyautogui.press('enter')

        return f"Éxito: Opera lanzado y búsqueda iniciada para '{termino_busqueda}'."

    except FileNotFoundError:
        return f"Error: No se pudo encontrar el ejecutable de Opera en '{opera_cmd}'. Verifique la instalación."
    except pyautogui.FailSafeException:
        return "Error: PyAutoGUI FailSafe activado (ratón en esquina). Operación cancelada por seguridad."
    except Exception as e:
        return f"Error inesperado durante la automatización: {str(e)}"

# Definición de la herramienta para Google Gemini Function Calling
TOOL_DEF = {
    "name": "abrir_y_buscar_opera",
    "description": "Abre el navegador Opera y busca un término específico en el motor de búsqueda predeterminado. Funciona en Windows, macOS y Linux.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "termino": {
                "type": "STRING",
                "description": "El término o frase a buscar en Opera."
            }
        },
        "required": ["termino"]
    }
}