from duckduckgo_search import DDGS

def web_search(parameters: dict) -> str:
    query = parameters.get("query", "")
    
    if not query:
        return "Error: No se proporcionó ningún término de búsqueda."
        
    try:
        # Hacemos la búsqueda y pedimos solo los 3 primeros resultados para ser rápidos
        resultados = DDGS().text(query, max_results=3)
        
        if not resultados:
            return f"No se encontraron resultados en internet para: {query}"
            
        # Empaquetamos la información para el cerebro de JARVIS
        reporte = f"Resultados de internet para '{query}':\n"
        for i, res in enumerate(resultados):
            reporte += f"{i+1}. {res['title']}: {res['body']}\n"
            
        return f"Búsqueda exitosa. Usa esta información para responderle al usuario de forma natural y conversacional: {reporte}"
        
    except Exception as e:
        return f"Error crítico de conexión al buscar en la red: {e}"