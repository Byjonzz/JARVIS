import os
import time
import glob

def abrir_gears_4(parameters: dict) -> str:
    action = parameters.get("action", "")
    if action != "launch":
        return "Acción no reconocida. Use 'action': 'launch'."
    
    try:
        # 1. Apuntamos a tu escritorio (usando la ruta que veo en tu consola)
        escritorio_path = r"C:\Users\bravo\OneDrive\Escritorio"
        
        # 2. El Radar: Busca cualquier archivo .lnk que tenga "Gears of War 4" en el nombre
        patron_busqueda = os.path.join(escritorio_path, "*Gears of War 4*.lnk")
        archivos_encontrados = glob.glob(patron_busqueda)
        
        # Si el radar está vacío...
        if not archivos_encontrados:
            return f"No encontré ningún acceso directo de Gears of War 4 en tu Escritorio. Por favor, crea el acceso directo usando shell:appsfolder."
        
        # 3. Tomamos el primer archivo que el radar haya encontrado
        gears_shortcut = archivos_encontrados[0]
        
        # 4. Lo ejecutamos
        os.startfile(gears_shortcut)
        
        time.sleep(2)
        nombre_archivo = os.path.basename(gears_shortcut)
        return f"Ejecutando protocolo de inicio para Gears of War 4 usando '{nombre_archivo}'..."
        
    except Exception as e:
        return f"Error al iniciar Gears of War 4: {str(e)}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "abrir_gears_4",
    "description": "Abre el juego Gears of War 4 en la computadora usando un radar de accesos directos. Úsalo SIEMPRE que el usuario te pida jugar o iniciar este título.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"action": {"type": "STRING", "description": "Siempre envía 'launch'"}},
        "required": ["action"]
    }
}