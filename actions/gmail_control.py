import webbrowser
import urllib.parse

def gmail_control(parameters: dict) -> str:
    action = parameters.get("action", "open").lower()
    
    if action == "draft":
        to = parameters.get("to", "")
        subject = parameters.get("subject", "")
        body = parameters.get("body", "")
        
        # Arma la estructura para abrir el redactor de correos
        url = f"mailto:{to}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"
        webbrowser.open(url)
        return f"Borrador de correo abierto y listo para enviar a: {to}"
    else:
        # Solo abre el correo para leer
        webbrowser.open("https://mail.google.com/mail/u/0/#inbox")
        return "Bandeja de entrada de Gmail abierta en el navegador."

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "gmail_control",
    "description": "Abre la bandeja de entrada de Gmail o redacta borradores de correo electrónico. Úsalo cuando el usuario quiera revisar su correo o redactar uno nuevo.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "Acción a realizar: 'open' (para leer correos) o 'draft' (para escribir uno)."},
            "to": {"type": "STRING", "description": "Dirección de correo electrónico del destinatario."},
            "subject": {"type": "STRING", "description": "Asunto del correo generado por ti."},
            "body": {"type": "STRING", "description": "Cuerpo completo del mensaje generado por ti."}
        },
        "required": ["action"]
    }
}   