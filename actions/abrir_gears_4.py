import subprocess
import time
import os

def abrir_gears_4(parameters: dict) -> str:
    action = parameters.get("action", "")
    if action != "launch":
        return "Acción no reconocida. Use 'action': 'launch'."
    
    try:
        # Ruta al ejecutable de Gears of War 4
        gears_path = r"C:\Program Files (x86)\Steam\steamapps\common\Gears of War 4\GearsOfWar4.exe"
        
        # Comprobar si el archivo existe
        if not os.path.exists(gears_path):
            return "Archivo no encontrado. Verifica la ruta."
        
        # Ejecutar el archivo .exe
        subprocess.Popen([gears_path])
        
        # Esperar un momento para asegurarse de que se abra
        time.sleep(5)
        
        return "Gears of War 4 se está iniciando..."
    except Exception as e:
        return f"Error al iniciar Gears of War 4: {str(e)}"

# Definición del diccionario para la API de Google Gemini
TOOL_DEF = {
    "name": "abrir_gears_4",
    "description": "Abre el juego Gears of War 4 directamente desde el sistema.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"action": {"type": "STRING"}},
        "required": ["action"]
    }
}