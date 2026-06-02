import subprocess


def open_app(parameters: dict) -> str:
    # Gemini nos enviará el nombre de la app dentro del diccionario
    app_name = parameters.get("app_name", "").lower()

    try:
        if "bloc" in app_name or "notepad" in app_name:
            subprocess.Popen(["notepad.exe"])
            return "Bloc de notas abierto con éxito en la pantalla."

        elif "calculadora" in app_name or "calc" in app_name:
            subprocess.Popen(["calc.exe"])
            return "Calculadora abierta con éxito."

        elif "explorador" in app_name or "archivos" in app_name:
            subprocess.Popen(["explorer.exe"])
            return "Explorador de archivos abierto."

        else:
            return f"No tengo configurado el comando exacto para abrir: {app_name}"

    except Exception as e:
        return f"Error interno al intentar abrir {app_name}: {e}"


TOOL_DEF = {
    "name": "open_app",
    "description": "Abre un programa o aplicación en la computadora.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app_name": {"type": "STRING", "description": "Nombre de la app"}
        },
        "required": ["app_name"],
    },
}
