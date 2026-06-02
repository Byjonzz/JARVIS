import os
import requests
import json

def auto_programmer(parameters: dict) -> str:
    request = parameters.get("request", "")
    tool_name = parameters.get("tool_name", "nueva_herramienta")
    
    # Aseguramos que el nombre sea válido para Python
    tool_name = tool_name.replace(" ", "_").lower()
    
    prompt = f"""
    Eres J.A.R.V.I.S., un Arquitecto de Software Senior en Python con nivel de acceso 'Modo Dios' al sistema operativo Windows.
    Tu objetivo es escribir el código Python para una nueva herramienta llamada '{tool_name}'.
    El usuario solicitó exactamente esto: {request}
    
    🔥 REGLAS DE CAPACIDAD ABSOLUTA (PROHIBIDO RENDIRSE):
    1. NUNCA digas que una tarea es "demasiado difícil", "compleja" o que "está fuera de tus capacidades". Eres capaz de automatizar cualquier cosa.
    2. Si el usuario pide interactuar con navegadores (como Opera, Chrome) o interfaces gráficas, usa la fuerza bruta:
       - Usa 'subprocess' o 'os' para abrir los programas `.exe`.
       - Usa 'time.sleep()' para darle tiempo a la computadora de abrir los programas.
       - Usa la librería 'pyautogui' o 'keyboard' para simular que escribes texto y presionas 'Enter'.
    
    ⚙️ REGLAS DE CÓDIGO ESTRICTAS:
    1. El código DEBE tener una función principal llamada exactamente '{tool_name}(parameters: dict) -> str'.
    2. La función DEBE retornar un string con el resultado final.
    3. Al final del archivo, DEBES declarar una variable llamada 'TOOL_DEF' que sea un diccionario con la estructura para la API de Google Gemini. 
       Ejemplo estricto: 
       TOOL_DEF = {{
           "name": "{tool_name}",
           "description": "Descripción detallada de lo que hace.",
           "parameters": {{
               "type": "OBJECT",
               "properties": {{"action": {{"type": "STRING"}}}},
               "required": ["action"]
           }}
       }}
    4. Devuelve ÚNICAMENTE el código Python puro, sin explicaciones ni saludos, dentro de un bloque ```python ... ```.
    """
    
    try:
        # 🟢 CONEXIÓN DIRECTA A TU OLLAMA LOCAL
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "qwen3.6:latest", # El modelo exacto que tienes en tu terminal
            "prompt": prompt,
            "stream": False
        }
        
        response = requests.post(url, json=payload)
        response.raise_for_status() # Verifica si hay error de conexión
        
        datos = response.json()
        texto = datos.get("response", "")
        
        # Extracción del código puro
        if "```python" in texto:
            codigo = texto.split("```python")[1].split("```")[0].strip()
        elif "```" in texto:
            codigo = texto.split("```")[1].split("```")[0].strip()
        else:
            codigo = texto.strip()
            
        ruta = os.path.join("actions", f"{tool_name}.py")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(codigo)
            
        return f"Éxito: Usé el procesamiento local de Ollama para programar la herramienta '{tool_name}.py'. Dile al usuario que reinicie la interfaz para cargarla."
        
    except requests.exceptions.ConnectionError:
        return "Error crítico: El servidor local de Ollama no está encendido. Dile al usuario que ejecute 'ollama serve' o 'ollama run qwen3.6' en su terminal."
    except Exception as e:
        return f"Error crítico en el auto-programador local: {e}"

# 🟢 EL MANUAL PARA EL AUTO-DESCUBRIMIENTO
TOOL_DEF = {
    "name": "auto_programmer",
    "description": "Permite a JARVIS escribir su propio código Python usando el modelo local Qwen en Ollama. Úsalo cuando el usuario te pida crear una nueva herramienta o automatizar algo complejo en Windows.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "request": {"type": "STRING", "description": "Descripción de lo que debe hacer el código."},
            "tool_name": {"type": "STRING", "description": "Nombre de la función en formato snake_case."}
        },
        "required": ["request", "tool_name"]
    }
}