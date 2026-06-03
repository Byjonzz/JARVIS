import os
import time

try:
    import pyautogui
except ImportError:
    pyautogui = None

def spotify_control(parameters: dict) -> str:
    query = parameters.get("query", "").strip()
    
    if not query:
        return "Error: No me dijiste qué canción o artista buscar."

    try:
        # Abre la aplicación de escritorio de Spotify usando su protocolo URI nativo
        uri = f"spotify:search:{query}"
        os.startfile(uri)
        
        if not pyautogui:
            return f"Abriendo Spotify buscando '{query}'. Falta {pyautogui} para darle Play automáticamente."

        # Esperamos a que Spotify cargue la búsqueda
        time.sleep(3)
        
        # Simulamos la tecla 'Tab' para enfocar el primer resultado y 'Enter' para reproducirlo
        pyautogui.press('tab', presses=2, interval=0.2)
        pyautogui.press('enter')
        
        return f"Reproduciendo '{query}' en tu cuenta de Spotify."
        
    except Exception as e:
        return f"Error intentando controlar Spotify: {e}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "spotify_control",
    "description": "Busca y reproduce música o podcasts en la aplicación de escritorio de Spotify. Úsalo cuando el usuario te pida poner música, una canción en específico o un artista.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "El nombre de la canción, artista o playlist a reproducir."}
        },
        "required": ["query"]
    }
}