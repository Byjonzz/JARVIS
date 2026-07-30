import subprocess
import sys
import json

def abrir_calculadora(parameters: dict) -> str:
    """
    Abre la calculadora de Windows (calc.exe).
    """
    try:
        # En Windows 10/11, 'calc' es un alias de la tienda (AppX), 
        # pero 'calc.exe' suele redirigir correctamente. 
        # Usar 'start' en shell=True es lo más robusto para apps UWP.
        if sys.platform == "win32":
            subprocess.Popen("start calc:", shell=True)
            return json.dumps({"status": "success", "message": "Calculadora de Windows abierta correctamente."})
        else:
            return json.dumps({"status": "error", "message": "Esta herramienta solo funciona en sistemas Windows."})
    except Exception as e:
        return json.dumps({"status": "error", "message": f"No se pudo abrir la calculadora: {str(e)}"})

TOOL_DEF = {
    "name": "abrir_calculadora",
    "description": "Abre la aplicación nativa de Calculadora en Windows.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
}