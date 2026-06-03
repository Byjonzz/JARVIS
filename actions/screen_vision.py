import os
from PIL import ImageGrab
from google import genai
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

def screen_vision(parameters: dict) -> str:
    question = parameters.get("question", "¿Qué hay en mi pantalla?")
    ruta_img = "temp_vision.png"
    image_ref = None
    
    try:
        # Toma una captura instantánea de todos tus monitores
        img = ImageGrab.grab(all_screens=True)
        img.save(ruta_img)
        
        client = genai.Client(api_key=API_KEY)
        import PIL.Image
        image_ref = PIL.Image.open(ruta_img)
        
        prompt_maestro = f"Eres JARVIS. Estás viendo la pantalla en vivo de la computadora del usuario. Responde a su pregunta basándote ÚNICAMENTE en la imagen. Pregunta: {question}. Sé conciso y directo."
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image_ref, prompt_maestro]
        )
            
        return f"Análisis de pantalla completado: {response.text}"
        
    except Exception as e:
        return f"Error en el módulo de visión: {e}"
        
    finally:
        # 🟢 FIX: El "Limpiaparabrisas" Absoluto. Garantiza que la imagen se borre del 
        # disco duro el 100% de las veces, incluso si se va el internet o crashea la API.
        if image_ref:
            try:
                # Tenemos que cerrar el archivo en PIL primero, o Windows no nos dejará borrarlo
                image_ref.close() 
            except Exception:
                pass
                
        if os.path.exists(ruta_img):
            try:
                os.remove(ruta_img)
            except Exception as e:
                print(f"[Visión] Advertencia: No se pudo limpiar el archivo temporal: {e}")

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