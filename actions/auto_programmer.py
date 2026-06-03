import os
import requests
import json
import re

def auto_programmer(parameters: dict) -> str:
    request = parameters.get("request", "")
    tool_name = parameters.get("tool_name", "nueva_herramienta")
    
    # Aseguramos que el nombre sea válido para Python
    tool_name = tool_name.replace(" ", "_").lower()
    
    prompt = f"""
    Eres J.A.R.V.I.S., un Arquitecto de Software Senior en Python con nivel de acceso 'Modo Dios'.
    Tu objetivo es escribir el código Python para una nueva herramienta llamada '{tool_name}'.
    El usuario solicitó exactamente esto: {request}
    
    🔥 REGLAS DE CAPACIDAD ABSOLUTA (PROHIBIDO RENDIRSE):
    1. NUNCA digas que una tarea es "demasiado difícil" o "compleja".
    2. Usa librerías nativas (subprocess, os, pyautogui) para lograr el objetivo a la fuerza bruta si es necesario.
    
    ⚙️ REGLAS DE CÓDIGO ESTRICTAS:
    1. El código DEBE tener una función principal llamada exactamente '{tool_name}(parameters: dict) -> str'.
    2. La función DEBE retornar un string con el resultado final.
    3. Al final del archivo, DEBES declarar la variable 'TOOL_DEF' con el formato de API de Google Gemini.
    4. Devuelve ÚNICAMENTE el código Python puro dentro de un bloque ```python ... ```.
    """
    
    try:
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "qwen2.5-coder:7b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_ctx": 8192
            }
        }
        
        # 🟢 FIX 1: El Seguro de Vida (Timeout). Si en 2 minutos no acaba, aborta la misión para no congelar a JARVIS.
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status() 
        
        datos = response.json()
        texto = datos.get("response", "")
        
        # 🟢 FIX 2: Extracción Indestructible por Regex
        bloques = re.findall(r'```python\n(.*?)\n```', texto, re.DOTALL)
        if bloques:
            codigo = bloques[0].strip()
        elif "```" in texto:
            codigo = texto.split("```")[1].split("```")[0].strip()
        else:
            codigo = texto.strip()
            
        ruta = os.path.join("actions", f"{tool_name}.py")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(codigo)
            
        return f"Éxito: Usé Ollama local para programar la herramienta '{tool_name}.py'. Dile al usuario que reinicie la interfaz para cargarla."
        
    except requests.exceptions.Timeout:
        return "Error crítico: Ollama tardó demasiado en generar el código y cancelé la conexión para evitar congelarme."
    except requests.exceptions.ConnectionError:
        return "Error crítico: El servidor local de Ollama no está encendido. Ejecuta 'ollama serve'."
    except Exception as e:
        return f"Error crítico en el auto-programador: {e}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "auto_programmer",
    "description": "Permite a JARVIS escribir su propio código Python usando el modelo local Qwen. Úsalo cuando el usuario te pida crear una nueva herramienta o automatizar algo complejo en Windows.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "request": {"type": "STRING", "description": "Descripción de lo que debe hacer el código."},
            "tool_name": {"type": "STRING", "description": "Nombre de la función en formato snake_case."}
        },
        "required": ["request", "tool_name"]
    }
}