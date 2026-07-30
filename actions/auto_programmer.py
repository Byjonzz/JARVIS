import os
import requests
import json
import re

# ⏱️ Límite que respeta main.py: el modelo razonador de OpenRouter tarda minutos
# en escribir una herramienta completa (el default de 30s lo mataba siempre).
TOOL_TIMEOUT = 300
# 🚀 main.py la ejecuta en segundo plano y anuncia por voz cuando termina de verdad.
TOOL_BACKGROUND = True

def auto_programmer(parameters: dict) -> str:
    request = parameters.get("request", "")
    tool_name = parameters.get("tool_name", "nueva_herramienta")
    
    # Aseguramos que el nombre sea válido para Python
    tool_name = tool_name.replace(" ", "_").lower()

    # 🔒 Esta herramienta SOLO CREA archivos nuevos. Sin este candado, pedir
    # "arregla os_control" con tool_name='os_control' SOBRESCRIBÍA la herramienta
    # existente con código generado desde cero (pasó de verdad: se perdió
    # minimize_all). Editar lo existente es trabajo de self_edit.
    ruta = os.path.join("actions", f"{tool_name}.py")
    if os.path.exists(ruta):
        return (f"Error: la herramienta '{tool_name}' YA EXISTE y auto_programmer solo crea "
                "herramientas nuevas. Para arreglarla o modificarla usa 'self_edit' con "
                f"target_file '{tool_name}.py'; para una alternativa nueva, elige otro nombre.")
    
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

        response = requests.post(url, headers=headers, json=payload, timeout=280)
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

        # 🛡️ Validar ANTES de escribir: código con error de sintaxis nunca cargaría
        # y el aviso por voz mentiría diciendo que la herramienta está lista.
        try:
            compile(codigo, ruta, "exec")
        except SyntaxError as e:
            return (f"Error: el código generado no compila (línea {e.lineno}: {e.msg}). "
                    "No escribí ningún archivo; conviene reintentar la creación.")

        with open(ruta, "w", encoding="utf-8") as f:
            f.write(codigo)

        return (f"Éxito: usé el modelo {modelo} para programar la herramienta '{tool_name}.py'. "
                "El sistema la cargará automáticamente: ya se puede usar, sin reiniciar nada.")

    except Exception as e:
        return f"Error crítico en el auto-programador conectado a OpenRouter: {e}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "auto_programmer",
    "description": (
        "Crea desde cero una herramienta NUEVA que aún no existe (escribe un archivo Python "
        "nuevo en actions/). Úsalo SOLO cuando el usuario pida crear o inventar una capacidad "
        "que no tienes. Si pide ARREGLAR, EDITAR o MEJORAR una herramienta o archivo que YA "
        "existe, NO uses esta: usa 'self_edit'. Tarda hasta 3 minutos: avisa al usuario de que "
        "trabajarás en ello y NO la llames dos veces por la misma petición."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "request": {"type": "STRING", "description": "Descripción de lo que debe hacer el código."},
            "tool_name": {"type": "STRING", "description": "Nombre de la función en formato snake_case."}
        },
        "required": ["request", "tool_name"]
    }
}