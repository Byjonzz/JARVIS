import os
from google import genai
import os
from dotenv import load_dotenv

# REEMPLAZA CON TU API KEY
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

def auto_programmer(parameters: dict) -> str:
    # Recibimos qué quiere el usuario y cómo se llamará el archivo
    request = parameters.get("request", "")
    tool_name = parameters.get("tool_name", "nueva_herramienta")
    
    # Aseguramos que el nombre sea válido para Python (sin espacios)
    tool_name = tool_name.replace(" ", "_").lower()
    
    # Le damos la instrucción a Gemini 2.5 para que actúe como programador
    prompt = f"""
    Eres un desarrollador Python experto. 
    Escribe el código Python para una nueva herramienta de un asistente virtual llamada '{tool_name}'.
    El usuario solicitó que haga esto: {request}
    
    REGLAS ESTRICTAS:
    1. El código DEBE tener una función principal llamada exactamente '{tool_name}(parameters: dict) -> str'.
    2. La función DEBE retornar un string con el resultado final.
    3. Devuelve ÚNICAMENTE el código Python, sin explicaciones, dentro de un bloque ```python ... ```.
    """
    
    try:
        client = genai.Client(api_key=API_KEY)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        # Extraemos solo el código, quitando el formato Markdown
        texto = response.text
        if "```python" in texto:
            codigo = texto.split("```python")[1].split("```")[0].strip()
        elif "```" in texto:
            codigo = texto.split("```")[1].split("```")[0].strip()
        else:
            codigo = texto.strip()
            
        # Creamos y guardamos el nuevo archivo en la carpeta actions/
        ruta = os.path.join("actions", f"{tool_name}.py")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(codigo)
            
        return f"Éxito: He programado la herramienta '{tool_name}.py' y la he guardado en tu carpeta de acciones. Dile al usuario que el código está listo y que debe conectarlo al cerebro principal."
        
    except Exception as e:
        return f"Error crítico en el auto-programador: {e}"