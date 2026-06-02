import pyautogui
import time


def computer_control(parameters: dict) -> str:
    action = parameters.get("action", "")
    text = parameters.get("text", "")
    keys = parameters.get("keys", "")

    try:
        # Le damos un pequeño respiro de 1 segundo para asegurarnos
        # de que la app a la que queremos escribirle ya cargó en pantalla
        time.sleep(1.0)

        if action == "type":
            # Escribe el texto simulando las teclas humanas
            pyautogui.write(text, interval=0.02)
            return f"Texto escrito exitosamente: '{text}'"

        elif action == "press":
            # Presiona una tecla específica como 'enter', 'esc', 'space'
            pyautogui.press(keys)
            return f"Tecla '{keys}' presionada."

        elif action == "hotkey":
            # Ejecuta atajos como 'ctrl+c' o 'alt+f4'
            keys_list = keys.split("+")
            pyautogui.hotkey(*keys_list)
            return f"Atajo de teclado ejecutado: {keys}"

        else:
            return f"Acción de control no soportada: {action}"

    except Exception as e:
        return f"Error al intentar controlar el teclado: {e}"


TOOL_DEF = {
    "name": "computer_control",
    "description": "Controla el teclado físico de la PC.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "type | press | hotkey"},
            "text": {"type": "STRING", "description": "El texto a escribir"},
            "keys": {"type": "STRING", "description": "Tecla a presionar o atajo"},
        },
        "required": ["action"],
    },
}
