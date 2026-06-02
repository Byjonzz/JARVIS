import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")


def auto_programmer(parameters: dict) -> str:
    request = parameters.get("request", "")
    tool_name = parameters.get("tool_name", "nueva_herramienta")

    # Aseguramos que el nombre sea válido para Python (sin espacios)
    tool_name = tool_name.replace(" ", "_").lower()

    prompt = f"""
    Eres un desarrollador Python experto. 
    Escribe el código Python para una nueva herramienta de un asistente virtual llamada '{tool_name}'.
    El usuario solicitó que haga esto: {request}
    
    REGLAS ESTRICTAS:
    1. El código DEBE tener una función principal llamada exactamente '{tool_name}(parameters: dict) -> str'.
    2. La función DEBE retornar un string con el resultado final.
    3. Al final del archivo, DEBES declarar una variable llamada 'TOOL_DEF' que sea un diccionario con la estructura de parámetros para la API de Google Gemini. 
    Ejemplo estricto: 
    TOOL_DEF = {{
        "name": "{tool_name}",
        "description": "Descripción de lo que hace.",
        "parameters": {{
            "type": "OBJECT",
            "properties": {{"action": {{"type": "STRING", "description": "ejecutar"}}}},
            "required": ["action"]
        }}
    }}
    4. Devuelve ÚNICAMENTE el código Python puro, sin explicaciones ni saludos, dentro de un bloque ```python ... ```.
    """

    try:
        client = genai.Client(api_key=API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        texto = response.text
        if "```python" in texto:
            codigo = texto.split("```python")[1].split("```")[0].strip()
        elif "```" in texto:
            codigo = texto.split("```")[1].split("```")[0].strip()
        else:
            codigo = texto.strip()

        ruta = os.path.join("actions", f"{tool_name}.py")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(codigo)

        return f"Éxito: He programado la herramienta '{tool_name}.py' y la he guardado en el sistema. Dile al usuario que la herramienta se cargará automáticamente la próxima vez que se reinicie la interfaz gráfica."

    except Exception as e:
        return f"Error crítico en el auto-programador: {e}"


TOOL_DEF = {
    "name": "auto_programmer",
    "description": "Permite a JARVIS escribir su propio código Python para crear nuevas herramientas. Úsalo cuando el usuario te pida que programes una nueva habilidad o herramienta.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "request": {
                "type": "STRING",
                "description": "Descripción de lo que debe hacer el código.",
            },
            "tool_name": {
                "type": "STRING",
                "description": "Nombre de la función en formato snake_case.",
            },
        },
        "required": ["request", "tool_name"],
    },
}
