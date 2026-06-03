import os
import sys
import requests
import traceback
import json
import time
import threading

def ejecutar_reinicio(archivo_modificado):
    time.sleep(5)
    print(f"\n🔄 [SISTEMA] Aplicando cambios de '{archivo_modificado}'. Reiniciando núcleo...")
    os.execl(sys.executable, sys.executable, *sys.argv)

def self_edit(parameters: dict) -> str:
    target_file = parameters.get("target_file", "").strip()
    request = parameters.get("request", "").strip()

    print(f"\n--- 🕵️‍♂️ [DEBUG] MODO DE EDICIÓN QUIRÚRGICA ---")
    nombre_archivo = os.path.basename(target_file)
    ruta_encontrada = None
    
    rutas_posibles = [nombre_archivo, os.path.join("actions", nombre_archivo), target_file]
    for ruta in rutas_posibles:
        if os.path.exists(ruta):
            ruta_encontrada = ruta
            break
            
    if not ruta_encontrada:
        return f"Error: No encontré el archivo '{nombre_archivo}'."

    try:
        with open(ruta_encontrada, "r", encoding="utf-8") as f:
            codigo_original = f.read().replace("\r\n", "\n")

        # 🧠 CONEXIÓN AL HIPOCAMPO
        memoria_texto = ""
        ruta_memoria = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "long_term_memory.json")
        if os.path.exists(ruta_memoria):
            try:
                with open(ruta_memoria, "r", encoding="utf-8") as f:
                    memoria = json.load(f)
                    if "hechos" in memoria and memoria["hechos"]:
                        memoria_texto = "REGLAS APRENDIDAS DEL USUARIO (DEBES OBEDECERLAS ESTRICTAMENTE):\n- " + "\n- ".join(memoria["hechos"])
            except Exception as e:
                print(f"[DEBUG] Error leyendo memoria: {e}")

        prompt = f'''
        Eres JARVIS, un Arquitecto de Software Senior. El usuario solicitó este cambio en '{ruta_encontrada}':
        "{request}"
        
        {memoria_texto}
        
        INSTRUCCIONES CRÍTICAS:
        1. NO reescribas todo el archivo.
        2. 🚫 ¡PROHIBIDO RENOMBRAR VARIABLES! Solo cambia sus valores internos.
        3. 🛡️ ¡EL FONDO ES SAGRADO!: NUNCA modifiques las variables `C_BG` ni `C_PANEL`. El fondo siempre debe ser negro o translúcido oscuro. Solo tienes permitido cambiar los colores de los acentos brillantes (ej. `C_PRI`, `C_PRI_DIM`, `C_BORDER`, `C_TEXT`, `GREEN_NEON`).
        4. El bloque [BUSCAR] debe ser un fragmento CONTINUO exacto. No te saltes líneas intermedias.
        
        [BUSCAR]
        codigo viejo exactamente como esta en el archivo, sin omitir lineas
        [REEMPLAZAR]
        codigo nuevo que quieres poner, MANTENIENDO los mismos nombres de variables y respetando el fondo oscuro.
        [FIN]
        
        Código actual de referencia:
        ```python
        {codigo_original}
        ```
        
        Responde ÚNICAMENTE con el formato indicado. Cero saludos.
        '''

        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "qwen2.5-coder:7b", 
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_ctx": 8192,
                "num_predict": 400, 
                "temperature": 0.0
            }
        }
        
        print(f"[DEBUG] Generando parche considerando el Hipocampo y el Escudo de Diseño...")
        response = requests.post(url, json=payload, stream=True)
        response.raise_for_status()
        
        texto_completo = ""
        for linea in response.iter_lines():
            if linea:
                datos = json.loads(linea)
                fragmento = datos.get("response", "")
                texto_completo += fragmento
                
                if "[FIN]" in texto_completo:
                    response.close()
                    break
                    
        print(f"\n[DEBUG] --- TEXTO CRUDO GENERADO POR LA IA ---")
        print(texto_completo.strip())
        print("----------------------------------------------\n")

        if "[BUSCAR]" in texto_completo and "[REEMPLAZAR]" in texto_completo:
            try:
                buscar = texto_completo.split("[BUSCAR]")[1].split("[REEMPLAZAR]")[0].strip("\n")
                reemplazar = texto_completo.split("[REEMPLAZAR]")[1].split("[FIN]")[0].strip("\n")
                
                buscar = buscar.replace("```python", "").replace("```", "").strip("\n")
                reemplazar = reemplazar.replace("```python", "").replace("```", "").strip("\n")
                
                if buscar in codigo_original:
                    codigo_nuevo = codigo_original.replace(buscar, reemplazar)
                    
                    with open(ruta_encontrada, "w", encoding="utf-8") as f:
                        f.write(codigo_nuevo)
                        
                    threading.Thread(target=ejecutar_reinicio, args=(nombre_archivo,), daemon=True).start()
                    return f"Archivo {nombre_archivo} modificado quirúrgicamente. Reiniciando núcleo..."
                else:
                    return "Error: La IA generó el bloque, pero el texto a BUSCAR no coincide. Revisa la consola."
            except Exception as e:
                return f"Error aplicando el parche: {e}"
        else:
            return "Error: La IA no usó el formato estricto de BUSCAR y REEMPLAZAR."

    except requests.exceptions.ConnectionError:
        return "Error: Ollama no está encendido."
    except Exception as e:
        traceback.print_exc()
        return f"Error crítico: {e}"

TOOL_DEF = {
    "name": "self_edit",
    "description": "Modifica archivos internos de JARVIS usando parches rápidos. Reinicia el sistema automáticamente.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target_file": {"type": "STRING"},
            "request": {"type": "STRING"}
        },
        "required": ["target_file", "request"]
    }
}