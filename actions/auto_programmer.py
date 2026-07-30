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
    
    # Modelo del programador: se puede cambiar con OPENROUTER_MODEL en .env
    modelo = (os.getenv("OPENROUTER_MODEL") or "nvidia/nemotron-3-ultra-550b-a55b:free").strip()

    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": modelo,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            # Los modelos razonadores (como Nemotron) devuelven su "pensamiento"
            # antes del código; esto lo excluye de la respuesta.
            "reasoning": {"exclude": True}
        }

        response = requests.post(url, headers=headers, json=payload, timeout=120)
        if response.status_code != 200:
            # El detalle del servidor (modelo inexistente, cuota agotada...) es lo
            # único que permite diagnosticar; sin esto solo veíamos "hubo un problema".
            return f"Error de OpenRouter (HTTP {response.status_code}): {response.text[:300]}"

        datos = response.json()
        if "choices" not in datos or not datos["choices"]:
            return f"OpenRouter respondió sin código: {str(datos)[:300]}"
        texto = datos["choices"][0]["message"]["content"] or ""

        # Extracción Indestructible por Regex (tolera ```py, ```python y saltos CRLF).
        # Se toma el ÚLTIMO bloque: si el modelo razona en voz alta, el código
        # definitivo es siempre el final.
        bloques = re.findall(r'```(?:python|py)?[ \t]*\r?\n(.*?)```', texto, re.DOTALL)
        if bloques:
            codigo = bloques[-1].strip()
        elif "```" in texto:
            codigo = texto.split("```")[1].split("```")[0].strip()
        else:
            codigo = texto.strip()

        if not codigo or "def " not in codigo:
            return ("El modelo no devolvió código Python utilizable. "
                    f"Empieza de su respuesta: {texto[:200]}")

        ruta = os.path.join("actions", f"{tool_name}.py")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(codigo)

        return (f"Éxito: usé el modelo {modelo} para programar la herramienta '{tool_name}.py'. "
                "Dile al usuario que reinicie la interfaz para cargarla.")

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