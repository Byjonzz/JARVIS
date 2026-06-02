import mss
from PIL import Image
from google import genai
import os
from dotenv import load_dotenv

# REEMPLAZA CON TU API KEY
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")


def screen_vision(parameters: dict) -> str:
    # Extraemos qué es lo que quieres saber sobre la pantalla
    question = parameters.get("question", "Describe brevemente qué hay en la pantalla.")
    action = parameters.get("action", "describe")

    prompt = f"El usuario te pregunta sobre su pantalla actual: '{question}'. Responde directo al grano, en español, y mantén tu actitud de JARVIS."

    try:
        # 1. Capturar la pantalla a velocidad extrema
        with mss.mss() as sct:
            # Seleccionamos el monitor principal
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)

            # Convertimos la captura en una imagen para la IA
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            # Reducimos la resolución a 720p para que suba a la nube en milisegundos
            img.thumbnail((1280, 720))

        # 2. Consultar al motor de visión de Gemini
        client = genai.Client(api_key=API_KEY)

        # Usamos el modelo rápido de 2.5
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=[prompt, img]
        )

        # Le pasamos el texto analizado de vuelta a la voz de JARVIS
        return f"Análisis visual exitoso. Respóndele esto al usuario usando la información: {response.text}"

    except Exception as e:
        return f"Error en el módulo óptico: {e}"


TOOL_DEF = {
    "name": "screen_vision",
    "description": "JARVIS puede VER la pantalla del usuario.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "describe | question | help",
            },
            "question": {
                "type": "STRING",
                "description": "Pregunta sobre la pantalla.",
            },
        },
        "required": ["action"],
    },
}
