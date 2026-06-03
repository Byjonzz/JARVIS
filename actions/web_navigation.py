import requests
from bs4 import BeautifulSoup

def web_navigation(parameters: dict) -> str:
    url = parameters.get("url", "").strip()
    if not url:
        return "Error: Debes proporcionar una URL válida."

    try:
        # Nos disfrazamos de navegador real para que no nos bloqueen
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extraemos solo el texto de los párrafos principales (evitamos basura visual)
        paragraphs = soup.find_all('p')
        text = " ".join([p.get_text() for p in paragraphs])
        
        # Limitamos a 2500 caracteres para no saturar la memoria a corto plazo de JARVIS
        if len(text) > 2500:
            text = text[:2500] + "... [Texto truncado. Resume esta información para el usuario]."
            
        return f"Contenido extraído de la página:\n\n{text}"
        
    except Exception as e:
        return f"Error al intentar leer la página web: {e}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "web_navigation",
    "description": "Navega a una URL específica, extrae el texto principal de la página web y lo lee. Úsalo si necesitas profundizar en un enlace obtenido en una búsqueda previa.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "url": {"type": "STRING", "description": "La dirección URL completa de la página web a leer (debe incluir http o https)."}
        },
        "required": ["url"]
    }
}