import os
import sys
import requests
import traceback
import json
import time
import threading
import re

def ejecutar_reinicio(archivo_modificado):
    time.sleep(12)
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
            codigo_original = f.read()

        prompt = f'''
        Eres JARVIS, un Arquitecto de Software Senior. El usuario solicitó este cambio en '{ruta_encontrada}':
        "{request}"
        
        Aquí está el código actual:
        ```python
        {codigo_original}
        ```
        
        INSTRUCCIONES CRÍTICAS (OPTIMIZACIÓN DE MEMORIA):
        1. ¡NO reescribas todo el archivo! Es una pérdida de tiempo y recursos.
        2. Encuentra la parte que debe cambiar y devuelve ÚNICAMENTE el bloque de reemplazo.
        3. El texto que pongas en "SEARCH" debe ser EXACTAMENTE idéntico al código original (respeta los espacios y saltos de línea).
        
        UTILIZA ESTRICTAMENTE ESTE FORMATO:
        <<<< SEARCH
        codigo viejo que quieres quitar
        ====
        codigo nuevo que quieres poner
        >>>> REPLACE
        
        Cero explicaciones, cero saludos. Ve directo al código.
        '''

        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "qwen2.5-coder:7b", # ⚡ Volvemos al modelo inteligente, ya no colapsará
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_ctx": 16000,
                "temperature": 0.1 # Temperatura baja para que sea un robot preciso
            }
        }
        
        response = requests.post(url, json=payload, stream=True)
        response.raise_for_status()
        
        texto_completo = ""
        for linea in response.iter_lines():
            if linea:
                datos = json.loads(linea)
                fragmento = datos.get("response", "")
                texto_completo += fragmento
                print(fragmento, end="", flush=True) 
                
                # 🛑 EL ASESINO DE BUCLES ACTUALIZADO
                if ">>>> REPLACE" in texto_completo and len(texto_completo.split(">>>> REPLACE")[-1]) > 50:
                    print("\n\n[DEBUG] 🛑 Fin de la edición detectado. Cortando...")
                    response.close()
                    break
                
        print("\n[DEBUG] Aplicando parches quirúrgicos al código...")

        # 🟢 EL BUSCADOR Y REEMPLAZADOR INTELIGENTE (REGEX)
        bloques = re.findall(r'<<<< SEARCH\n(.*?)\n====\n(.*?)\n>>>> REPLACE', texto_completo, re.DOTALL)
        
        if bloques:
            codigo_nuevo = codigo_original
            cambios_exitosos = 0
            for original, nuevo in bloques:
                # Comprueba si el fragmento exacto existe en el archivo
                if original in codigo_nuevo:
                    codigo_nuevo = codigo_nuevo.replace(original, nuevo)
                    cambios_exitosos += 1
                else:
                    print("\n❌ [DEBUG] Advertencia: No se encontró la coincidencia exacta de SEARCH.")
                    
            if cambios_exitosos == 0:
                return "Error: La IA propuso cambios, pero el texto a reemplazar no coincidía exactamente con el archivo original."
        else:
            # 🛡️ PLAN B: Por si la IA ignora las reglas y decide reescribir todo
            if "```python" in texto_completo:
                codigo_nuevo = texto_completo.split("```python")[1].split("```")[0].strip()
            elif "```" in texto_completo:
                codigo_nuevo = texto_completo.split("```")[1].split("```")[0].strip()
            else:
                return "Error: La IA no usó el formato de parche ni escribió código estándar."

        with open(ruta_encontrada, "w", encoding="utf-8") as f:
            f.write(codigo_nuevo)
            
        threading.Thread(target=ejecutar_reinicio, args=(nombre_archivo,), daemon=True).start()

        if "ui.py" in nombre_archivo.lower():
            return "Interfaz gráfica modificada quirúrgicamente. Reiniciando ventana..."
        else:
            return f"Archivo '{nombre_archivo}' parcheado con éxito. Reiniciando núcleo..."

    except requests.exceptions.ConnectionError:
        return "Error: Ollama no está encendido."
    except Exception as e:
        traceback.print_exc()
        return f"Error crítico durante la modificación: {e}"

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "self_edit",
    "description": "Modifica archivos internos de JARVIS (como ui.py o guardia.py) usando parches de código rápidos. Reinicia el sistema automáticamente al terminar.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target_file": {"type": "STRING", "description": "Nombre del archivo a modificar."},
            "request": {"type": "STRING", "description": "Cambio solicitado."}
        },
        "required": ["target_file", "request"]
    }
}