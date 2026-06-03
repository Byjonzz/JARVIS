import psutil

def system_monitor(parameters: dict) -> str:
    try:
        # Leemos los sensores en tiempo real
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        bateria = psutil.sensors_battery()
        
        reporte = f"🖥️ Reporte del Hardware:\n- Uso de CPU: {cpu}%\n- Memoria RAM: {ram.percent}% usada ({ram.available / (1024**3):.1f} GB libres)\n"
        
        # Si tienes laptop, leemos la batería
        if bateria:
            enchufado = "conectada a la corriente" if bateria.power_plugged else "usando batería"
            reporte += f"- Batería: {bateria.percent}% ({enchufado})\n"
            
        return reporte
    except Exception as e:
        return f"Error leyendo los sensores del sistema: {e}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "system_monitor",
    "description": "Revisa el estado del hardware de la computadora (Uso de CPU, RAM, y Batería). Úsalo cuando el usuario pregunte por el rendimiento, la memoria disponible o cuánta batería le queda.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "estado"}
        },
        "required": ["action"]
    }
}