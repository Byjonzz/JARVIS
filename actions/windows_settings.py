import os
import subprocess

def windows_settings(parameters: dict) -> str:
    action = parameters.get("action", "").lower()
    value = parameters.get("value", "")

    try:
        if action == "brightness":
            valor = str(value).strip().replace("%", "")
            if not valor.isdigit() or not (0 <= int(valor) <= 100):
                return "Error: el brillo debe ser un número entre 0 y 100."
            # Inyecta un comando a la BIOS/WMI para cambiar el brillo
            cmd = f'powershell -NoProfile "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{int(valor)})"'
            resultado = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
            if resultado.returncode != 0:
                return ("No se pudo cambiar el brillo: este monitor no expone control WMI "
                        "(suele pasar con monitores externos de escritorio).")
            return f"Brillo de la pantalla ajustado al {valor}%."
            
        elif action == "lock_screen":
            # Llama a la librería nativa de Windows para bloquear sesión
            os.system("rundll32.exe user32.dll,LockWorkStation")
            return "Pantalla de Windows bloqueada por seguridad."
            
        else:
            return f"Acción de configuración no soportada: {action}"
            
    except Exception as e:
        return f"Error cambiando configuración de Windows: {e}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "windows_settings",
    "description": "Cambia configuraciones nativas de Windows como el brillo de la pantalla o bloquear la computadora inmediatamente.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "Acción a realizar: 'brightness' o 'lock_screen'"},
            "value": {"type": "STRING", "description": "El nivel de porcentaje en números (ej. 50) si la acción es brightness."}
        },
        "required": ["action"]
    }
}