import os
import shutil

def smart_file_organizer(parameters: dict) -> str:
    # Por defecto, limpiará la carpeta de descargas del usuario
    target_folder = parameters.get("folder", os.path.join(os.path.expanduser("~"), "Downloads"))
    
    if not os.path.exists(target_folder):
        return f"La carpeta {target_folder} no existe."

    # Diccionario de categorías y extensiones
    categorias = {
        "Imágenes": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"],
        "Documentos": [".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv"],
        "Instaladores": [".exe", ".msi", ".apk"],
        "Código": [".py", ".js", ".html", ".css", ".json", ".sql", ".php", ".vue"],
        "Comprimidos": [".zip", ".rar", ".7z", ".tar", ".gz"]
    }

    archivos_movidos = 0

    try:
        for archivo in os.listdir(target_folder):
            ruta_completa = os.path.join(target_folder, archivo)
            
            # Solo procesamos archivos, no carpetas
            if os.path.isfile(ruta_completa):
                _, extension = os.path.splitext(archivo)
                extension = extension.lower()
                
                # Buscamos a qué categoría pertenece el archivo
                carpeta_destino = "Otros"
                for cat, exts in categorias.items():
                    if extension in exts:
                        carpeta_destino = cat
                        break
                        
                # Creamos la subcarpeta si no existe
                ruta_destino = os.path.join(target_folder, carpeta_destino)
                os.makedirs(ruta_destino, exist_ok=True)
                
                # Movemos el archivo
                shutil.move(ruta_completa, os.path.join(ruta_destino, archivo))
                archivos_movidos += 1
                
        return f"Limpieza completada. JARVIS organizó {archivos_movidos} archivos en la carpeta {target_folder}."
        
    except Exception as e:
        return f"Error organizando archivos: {e}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "smart_file_organizer",
    "description": "Organiza automáticamente una carpeta (por defecto 'Descargas') agrupando los archivos en subcarpetas según su tipo (Imágenes, Documentos, Código, Instaladores). Úsalo cuando el usuario pida limpiar o acomodar sus archivos.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "folder": {"type": "STRING", "description": "Ruta de la carpeta a limpiar. Si el usuario no especifica, déjalo vacío para limpiar 'Descargas'."}
        }
    }
}