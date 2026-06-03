from duckduckgo_search import DDGS

def web_search(parameters: dict) -> str:
    query = parameters.get("query", "").strip()
    if not query:
        return "Error: Debes proporcionar una consulta de búsqueda."
        
    try:
        resultados = []
        # Buscamos en DuckDuckGo de forma silenciosa
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=3):
                resultados.append(f"Título: {r.get('title')}\nResumen: {r.get('body')}\nEnlace: {r.get('href')}")
                
        if not resultados:
            return f"No se encontraron resultados en internet para: {query}"
            
        texto_final = f"Resultados encontrados para '{query}':\n\n" + "\n---\n".join(resultados)
        return texto_final
        
    except Exception as e:
        return f"Error en la búsqueda web: {e}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "web_search",
    "description": "Busca información actualizada en internet usando un motor de búsqueda. Devuelve un resumen de los primeros 3 resultados. Úsalo cuando el usuario haga preguntas sobre datos recientes, noticias, o información que no sepas.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Lo que se va a buscar en internet."}
        },
        "required": ["query"]
    }
}