import os
import subprocess

def windows_settings(parameters: dict) -> str:
    action = parameters.get("action", "").lower()
    value = parameters.get("value", "")

    try:
        if action == "brightness":
            # Inyecta un comando a la BIOS/WMI para cambiar el brillo
            cmd = f'powershell (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{value})'
            subprocess.run(cmd, shell=True)
            return f"Brillo de la pantalla ajustado al {value}%."
            
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