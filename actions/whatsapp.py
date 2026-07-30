import time
import urllib.parse
import webbrowser
import json
from pathlib import Path
import unicodedata

try:
    import pyautogui
except ImportError:
    pyautogui = None

BASE_DIR = Path(__file__).resolve().parent.parent
CONTACTS_FILE = BASE_DIR / "config" / "whatsapp_contacts.json"

def load_contacts() -> dict:
    if CONTACTS_FILE.exists():
        try:
            return json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_contacts(contacts: dict):
    try:
        CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONTACTS_FILE.write_text(json.dumps(contacts, indent=4, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[WhatsApp] Error saving contacts: {e}")

def clean_text(text):
    if not text: return ""
    text = text.lower()
    text = "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    return text

def whatsapp(parameters: dict) -> str:
    action = parameters.get("action", "").lower()
    receiver = parameters.get("receiver", "")
    message = parameters.get("message", "")  # El mensaje se envía tal cual (con acentos y mayúsculas)
    name = parameters.get("name", "")
    phone_param = parameters.get("phone", "")

    contacts = load_contacts()

    if action == "add_contact":
        contact_name = name or receiver
        if not contact_name or not phone_param:
            return "Error: Se requiere el nombre ('name') y el teléfono ('phone')."
        contact_phone = "".join(filter(str.isdigit, phone_param))
        contacts[contact_name.lower()] = {"name": contact_name, "phone": contact_phone}
        save_contacts(contacts)
        return f"Contacto '{contact_name}' guardado exitosamente con el teléfono: {contact_phone}."

    elif action == "delete_contact":
        contact_name = name or receiver
        if contact_name.lower() in contacts:
            del contacts[contact_name.lower()]
            save_contacts(contacts)
            return f"Contacto '{contact_name}' eliminado de JARVIS."
        return f"No se encontró el contacto '{contact_name}'."

    elif action == "list_contacts":
        if not contacts: return "No tienes contactos guardados."
        res = "Contactos en JARVIS:\n" + "\n".join([f"• {v['name']}: {v['phone']}" for v in contacts.values()])
        return res

    elif action in ["send", "send_text"]:
        if not receiver:
            return "Error: No se especificó el destinatario."
        
        phone = ""
        contact_name = receiver
        
        cleaned_receiver = "".join(c for c in receiver if c.isdigit() or c == '+')
        if sum(c.isdigit() for c in cleaned_receiver) >= 8:
            phone = cleaned_receiver.replace("+", "")
        else:
            for k, v in contacts.items():
                if receiver.lower() in k or k in receiver.lower():
                    phone = v["phone"]
                    contact_name = v["name"]
                    break
        
        encoded_msg = urllib.parse.quote(message) if message else ""
        url = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_msg}" if phone else f"https://web.whatsapp.com/send?text={encoded_msg}"
            
        webbrowser.open(url)
        
        if not pyautogui:
            return "WhatsApp abierto. Falta instalar 'pyautogui' para envío automático."

        # Esperamos a que el navegador cargue la sesión
        time.sleep(12)
        
        try:
            if not phone:
                pyautogui.hotkey('ctrl', 'alt', '/')
                time.sleep(1)
                pyautogui.hotkey('ctrl', 'a')
                pyautogui.press('backspace')
                pyautogui.write(receiver, interval=0.01)
                time.sleep(2)
                pyautogui.press('enter')
                time.sleep(1)

            if message:
                pyautogui.press('enter')
                time.sleep(1)
            
            return f"Mensaje enviado a '{contact_name}' vía WhatsApp."
        except Exception as e:
            return f"Error simulando teclas: {e}"

    elif action == "read":
        webbrowser.open("https://web.whatsapp.com")
        return "Abriendo WhatsApp Web para leer mensajes."

    return f"Acción '{action}' ejecutada."

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "whatsapp",
    "description": "Gestor de WhatsApp Web. Guarda contactos y automatiza el envío de mensajes. Úsalo para mandar un WhatsApp cuando el usuario te lo pida.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "Acción a realizar: send, add_contact, delete_contact, list_contacts, read"},
            "receiver": {"type": "STRING", "description": "Nombre o número del destinatario (solo para 'send')"},
            "message": {"type": "STRING", "description": "El texto del mensaje a enviar."},
            "phone": {"type": "STRING", "description": "Número de teléfono (solo para 'add_contact')."},
            "name": {"type": "STRING", "description": "Nombre del contacto (solo para 'add_contact' o 'delete_contact')."}
        },
        "required": ["action"]
    }
}