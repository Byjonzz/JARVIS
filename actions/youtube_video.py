import pywhatkit

def youtube_video(parameters: dict) -> str:
    query = parameters.get("query", "").strip()
    
    if not query:
        return "Error: No especificaste qué video o canción buscar en YouTube."

    try:
        # Esto abrirá el navegador y reproducirá el primer resultado automáticamente
        pywhatkit.playonyt(query)
        return f"Éxito: Reproduciendo '{query}' en YouTube. Dile al usuario que el video está iniciando."
    except Exception as e:
        return f"Error al intentar reproducir en YouTube: {e}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "youtube_video",
    "description": "Busca y reproduce videos o canciones directamente en YouTube abriendo el navegador. Úsalo cuando el usuario te pida poner música, buscar un tutorial o ver un video.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "El nombre del video, canción o artista que se va a buscar en YouTube."}
        },
        "required": ["query"]
    }
}