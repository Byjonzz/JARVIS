import os
from PIL import ImageGrab
from google import genai
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

def screen_vision(parameters: dict) -> str:
    question = parameters.get("question", "¿Qué hay en mi pantalla?")
    ruta_img = "temp_vision.png"
    
    try:
        # 1. Toma una captura instantánea de todos tus monitores
        img = ImageGrab.grab(all_screens=True)
        img.save(ruta_img)
        
        # 2. Carga el archivo para la IA
        client = genai.Client(api_key=API_KEY)
        import PIL.Image
        image_ref = PIL.Image.open(ruta_img)
        
        prompt_maestro = f"Eres JARVIS. Estás viendo la pantalla en vivo de la computadora del usuario. Responde a su pregunta basándote ÚNICAMENTE en la imagen. Pregunta: {question}. Sé conciso y directo."
        
        # 3. Le pedimos al modelo visual que analice tu pantalla
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image_ref, prompt_maestro]
        )
        
        # Opcional: borra la captura para no ocupar espacio
        if os.path.exists(ruta_img): os.remove(ruta_img)
            
        return f"Análisis de pantalla completado: {response.text}"
        
    except Exception as e:
        return f"Error en el módulo de visión: {e}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "screen_vision",
    "description": "Toma una captura invisible de la pantalla actual del usuario y usa Inteligencia Artificial visual para responder preguntas sobre lo que él está viendo (lee código, encuentra errores, describe imágenes). Úsalo cuando el usuario diga 'mira mi pantalla' o 'revisa este código'.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "question": {"type": "STRING", "description": "La pregunta específica que el usuario tiene sobre lo que hay en su pantalla."}
        },
        "required": ["question"]
    }
}