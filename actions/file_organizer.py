import os
import hashlib


def get_file_checksum(filepath):
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def file_organizer(args):
    folder_path = args.get("folder_path", "")
    action = args.get("action", "")

    if not folder_path or not os.path.exists(folder_path):
        return f"La ruta '{folder_path}' no existe o no fue especificada."

    if action == "find_duplicates":
        hashes = {}
        duplicados = []
        errores = 0
        # Escaneamos la carpeta
        for root, dirs, files in os.walk(folder_path):
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    file_hash = get_file_checksum(filepath)

                    if file_hash in hashes:
                        os.remove(filepath)  # ⚠️ Borra el duplicado directamente
                        duplicados.append(filepath)
                    else:
                        hashes[file_hash] = filepath
                except Exception:
                    errores += 1  # Archivo bloqueado o sin permisos: lo saltamos

        reporte = f"Escaneo completado. Se eliminaron {len(duplicados)} archivos duplicados para liberar espacio."
        if errores:
            reporte += f" ({errores} archivos no se pudieron leer y fueron ignorados)."
        return reporte

    return f"Acción '{action}' no reconocida. Usa 'find_duplicates'."


TOOL_DEF = {
    "name": "file_organizer",
    "description": "Escanea una carpeta en el disco duro para buscar y eliminar archivos duplicados exactos usando sumas de verificación MD5.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "find_duplicates"},
            "folder_path": {
                "type": "STRING",
                "description": "La ruta absoluta de la carpeta a limpiar en Windows.",
            },
        },
        "required": ["action", "folder_path"],
    },
}
