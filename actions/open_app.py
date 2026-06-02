import os
import subprocess
import webbrowser

def find_executable(app_name: str) -> str:
    """Escanea las carpetas del sistema para encontrar el ejecutable o acceso directo."""
    exe_search_dirs = [
        os.environ.get("ProgramFiles", "C:\\Program Files"),
        os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
        os.path.join(os.environ.get("LocalAppData", ""), "Programs"),
        "C:\\Windows\\System32",
        os.path.join(os.path.expanduser("~"), "Desktop")
    ]
    
    app_lower = app_name.lower().strip()
    
    for base_dir in exe_search_dirs:
        if not base_dir or not os.path.exists(base_dir): continue
        for root, dirs, files in os.walk(base_dir):
            if root.count(os.sep) - base_dir.count(os.sep) > 3:
                dirs.clear() # No buscar demasiado profundo para no trabar la PC
                continue
            for file in files:
                if file.lower().endswith((".exe", ".lnk")):
                    file_name_no_ext = os.path.splitext(file)[0].lower()
                    if app_lower == file_name_no_ext or app_lower in file_name_no_ext:
                        full_path = os.path.join(root, file)
                        if "uninstall" not in full_path.lower():
                            return full_path
    return None

def open_app(parameters: dict) -> str:
    app_name = parameters.get("app_name", "").strip()
    if not app_name:
        return "Error: Me debes decir qué aplicación abrir."

    app_lower = app_name.lower()

    try:
        # 1. Abrir URLs
        if app_lower.startswith("http") or app_lower.endswith((".com", ".org", ".net", ".es", ".cl")):
            url = app_name if app_lower.startswith("http") else f"https://{app_name}"
            webbrowser.open(url)
            return f"Abriendo el sitio web: {url}"

        # 2. Carpetas locales
        if os.path.exists(app_name) and os.path.isdir(app_name):
            os.startfile(app_name)
            return f"Abriendo la carpeta: {app_name}"

        # 3. Carpetas de usuario rápidas
        home = os.path.expanduser("~")
        virtual_folders = {
            "escritorio": os.path.join(home, "Desktop"),
            "descargas": os.path.join(home, "Downloads"),
            "documentos": os.path.join(home, "Documents"),
            "musica": os.path.join(home, "Music"),
            "videos": os.path.join(home, "Videos")
        }
        if app_lower in virtual_folders:
            os.startfile(virtual_folders[app_lower])
            return f"Abriendo carpeta del sistema: {app_lower}"

        # 4. Programas clásicos de Windows
        mappings = {
            "bloc de notas": "notepad.exe", "calculadora": "calc.exe", "chrome": "chrome.exe", 
            "explorador": "explorer.exe", "cmd": "cmd.exe", "powershell": "powershell.exe",
            "word": "winword.exe", "excel": "excel.exe", "opera": "opera.exe"
        }
        
        executable = mappings.get(app_lower)
        
        # 5. Si no lo conoce, usa el escáner heurístico
        if not executable:
            executable = find_executable(app_name)

        if not executable:
            executable = app_name # Último intento a fuerza bruta

        # 6. Ejecutar
        try:
            os.startfile(executable)
        except Exception:
            cmd_exec = f'"{executable}"' if " " in executable and not executable.startswith('"') else executable
            subprocess.Popen(cmd_exec, shell=True)

        return f"Aplicación o sitio '{app_name}' iniciada correctamente."
    except Exception as e:
        return f"Error intentando abrir '{app_name}': {str(e)}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "open_app",
    "description": "Abre aplicaciones instaladas en la computadora, carpetas del sistema, o sitios web en el navegador. Usa esta herramienta cuando el usuario pida abrir un programa o ir a una URL.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app_name": {"type": "STRING", "description": "El nombre del programa (ej: excel, chrome, opera), nombre de la carpeta (ej: descargas, documentos) o la URL del sitio web."}
        },
        "required": ["app_name"]
    }
}