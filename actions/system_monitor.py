import psutil

def system_monitor(parameters: dict) -> str:
    # parameters no se usa mucho aquí porque la acción siempre es leer el sistema,
    # pero lo recibimos para mantener la misma estructura que las demás herramientas.
    
    try:
        # psutil.cpu_percent necesita un pequeño intervalo para calcular el uso real
        cpu_usage = psutil.cpu_percent(interval=0.5)
        
        # Leemos la memoria RAM y la convertimos de bytes a Gigabytes
        ram = psutil.virtual_memory()
        ram_percent = ram.percent
        ram_free_gb = round(ram.available / (1024 ** 3), 2)
        ram_total_gb = round(ram.total / (1024 ** 3), 2)
        
        # Leemos el disco local C:
        disk = psutil.disk_usage('C:\\')
        disk_percent = disk.percent
        disk_free_gb = round(disk.free / (1024 ** 3), 2)
        
        # Construimos el reporte para que la IA lo lea y te lo resuma
        report = (
            f"DATOS DE SENSORES DEL SISTEMA:\n"
            f"- Uso de CPU: {cpu_usage}%\n"
            f"- Memoria RAM: Usando el {ram_percent}% ({ram_free_gb} GB libres de {ram_total_gb} GB totales)\n"
            f"- Almacenamiento Disco C: Usando el {disk_percent}% ({disk_free_gb} GB libres)"
        )
        
        return f"Lectura exitosa. Dale este reporte al usuario de forma natural y fluida: {report}"
        
    except Exception as e:
        return f"Error crítico al intentar acceder a los sensores del sistema: {e}"