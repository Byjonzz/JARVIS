from duckduckgo_search import DDGS
import time

def web_search(parameters: dict) -> str:
    query = parameters.get("query", "").strip()
    if not query:
        return "Error: Debes proporcionar una consulta de búsqueda."
        
    try:
        resultados = []
        # Usamos backend html para mayor estabilidad y añadimos timeout
        with DDGS(timeout=20) as ddgs:
            for r in ddgs.text(query, max_results=3, backend="html"):
                title = r.get('title', 'Sin título')
                body = r.get('body', 'Sin resumen')
                href = r.get('href', 'Sin enlace')
                resultados.append(f"Título: {title}\nResumen: {body}\nEnlace: {href}")
                
        if not resultados:
            return f"No se encontraron resultados en internet para: {query}"
            
        texto_final = f"Resultados encontrados para '{query}':\n\n" + "\n---\n".join(resultados)
        return texto_final
        
    except Exception as e:
        # Fallback: intentar con backend lite si html falla
        try:
            resultados = []
            with DDGS(timeout=20) as ddgs:
                for r in ddgs.text(query, max_results=3, backend="lite"):
                    title = r.get('title', 'Sin título')
                    body = r.get('body', 'Sin resumen')
                    href = r.get('href', 'Sin enlace')
                    resultados.append(f"Título: {title}\nResumen: {body}\nEnlace: {href}")
            
            if not resultados:
                return f"No se encontraron resultados en internet para: {query}"
                
            texto_final = f"Resultados encontrados para '{query}':\n\n" + "\n---\n".join(resultados)
            return texto_final
        except Exception as e2:
            return f"Error en la búsqueda web: {e2}"

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