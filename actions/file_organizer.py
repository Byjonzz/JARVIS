import os
import hashlib

def get_file_checksum(filepath):
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def file_organizer(args):
    folder_path = args.get("folder_path")
    action = args.get("action")
    
    if not os.path.exists(folder_path):
        return f"La ruta {folder_path} no existe."

    if action == "find_duplicates":
        hashes = {}
        duplicados = []
        # Escaneamos la carpeta
        for root, dirs, files in os.walk(folder_path):
            for filename in files:
                filepath = os.path.join(root, filename)
                file_hash = get_file_checksum(filepath)
                
                if file_hash in hashes:
                    duplicados.append(filepath)
                    os.remove(filepath) # ⚠️ Borra el duplicado directamente
                else:
                    hashes[file_hash] = filepath
                    
        return f"Escaneo completado. Se eliminaron {len(duplicados)} archivos duplicados para liberar espacio."