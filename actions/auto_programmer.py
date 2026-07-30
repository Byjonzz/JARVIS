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
    Eres I.R.I.S., un Arquitecta de Software Senior en Python con nivel de acceso 'Modo Dios'.
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
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "openai/gpt-oss-120b:free", # 🟢 Aquí está tu modelo gratuito
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status() 
        
        datos = response.json()
        texto = datos["choices"][0]["message"]["content"]
        
        # Extracción Indestructible por Regex (tolera ```py, ```python y saltos CRLF)
        bloques = re.findall(r'```(?:python|py)?[ \t]*\r?\n(.*?)```', texto, re.DOTALL)
        if bloques:
            codigo = bloques[0].strip()
        elif "```" in texto:
            codigo = texto.split("```")[1].split("```")[0].strip()
        else:
            codigo = texto.strip()
            
        ruta = os.path.join("actions", f"{tool_name}.py")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(codigo)
            
        return f"Éxito: Usé el modelo OpenRouter gpt-oss-120b para programar la herramienta '{tool_name}.py'. Dile al usuario que reinicie la interfaz para cargarla."
        
    except Exception as e:
        return f"Error crítico en el auto-programador conectado a OpenRouter: {e}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "auto_programmer",
    "description": "Permite a I.R.I.S. escribir su propio código Python usando OpenRouter. Úsalo cuando el usuario te pida crear una nueva herramienta o automatizar algo complejo en Windows.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "request": {"type": "STRING", "description": "Descripción de lo que debe hacer el código."},
            "tool_name": {"type": "STRING", "description": "Nombre de la función en formato snake_case."}
        },
        "required": ["request", "tool_name"]
    }
}