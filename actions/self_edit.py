import os
import sys
import requests
import traceback
import json
import time
import threading
import subprocess
import re

def ejecutar_reinicio(archivo_modificado):
    time.sleep(6)
    print(f"\n🔄 [SISTEMA] Aplicando cambios de '{archivo_modificado}'. Reiniciando núcleo...")
    subprocess.Popen([sys.executable] + sys.argv)
    os._exit(0)

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
        Eres JARVIS, un Arquitecto de Software Senior.
        
        Aquí está el código actual de referencia del archivo '{ruta_encontrada}':
        ```python
        {codigo_original}
        ```
        
        El usuario ha solicitado este cambio: "{request}"
        
        {memoria_texto}
        
        INSTRUCCIONES CRÍTICAS FINALES:
        1. 🚫 ¡PROHIBIDO INVENTAR NOMBRES DE VARIABLES! Usa exactamente las que están en el código de arriba (ej. C_PRI, C_PRI_DIM, NEON).
        2. 🛡️ ¡EL FONDO ES SAGRADO!: NUNCA modifiques las variables `C_BG` ni `C_PANEL`.
        
        RESPONDE ESTRICTAMENTE USANDO ESTE FORMATO:
        [BUSCAR]
        (codigo viejo exacto)
        [REEMPLAZAR]
        (codigo nuevo manteniendo nombres de variables)
        [FIN]
        
        Empieza ahora, sin saludos.
        '''

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "openai/gpt-oss-120b:free", # 🟢 Aquí está tu modelo gratuito
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0
        }
        
        print(f"[DEBUG] Generando parche con OpenRouter...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        datos = response.json()
        texto_completo = datos["choices"][0]["message"]["content"]
                    
        print(f"\n[DEBUG] --- TEXTO CRUDO GENERADO POR LA IA ---")
        print(texto_completo.strip())
        print("----------------------------------------------\n")

        codigo_nuevo = codigo_original
        cambios_aplicados = 0

        # PLAN A: Formato Correcto
        if "[BUSCAR]" in texto_completo and "[REEMPLAZAR]" in texto_completo:
            buscar = texto_completo.split("[BUSCAR]")[1].split("[REEMPLAZAR]")[0].strip("\n").replace("```python", "").replace("```", "")
            reemplazar = texto_completo.split("[REEMPLAZAR]")[1].split("[FIN]")[0].strip("\n").replace("```python", "").replace("```", "")
            
            if buscar in codigo_original and buscar.strip() != "":
                codigo_nuevo = codigo_original.replace(buscar, reemplazar)
                cambios_aplicados += 1
                print("[DEBUG] Reemplazo exacto exitoso.")
            else:
                # PLAN B: Parche Regex
                print("[DEBUG] Activando Parche Inteligente (Regex)...")
                reemplazar_lines = [l for l in reemplazar.split('\n') if l.strip()]
                for linea_nueva in reemplazar_lines:
                    if "=" in linea_nueva:
                        var_name = linea_nueva.split("=")[0].strip()
                        patron = r'^' + re.escape(var_name) + r'\s*=.*$'
                        codigo_nuevo_temp, num_subs = re.subn(patron, linea_nueva, codigo_nuevo, flags=re.MULTILINE)
                        if num_subs > 0:
                            codigo_nuevo = codigo_nuevo_temp
                            cambios_aplicados += 1
                            print(f"[DEBUG] Variable '{var_name}' parcheada.")

        # PLAN C: Extractor Crudo
        else:
            print("[DEBUG] Plan C (Extractor Crudo)...")
            bloques_codigo = re.findall(r'```(?:python|py)?[ \t]*\r?\n(.*?)```', texto_completo, re.DOTALL)
            texto_a_procesar = bloques_codigo[0] if bloques_codigo else texto_completo
            
            reemplazar_lines = [l for l in texto_a_procesar.split('\n') if l.strip()]
            for linea_nueva in reemplazar_lines:
                if "=" in linea_nueva and "==" not in linea_nueva:
                    var_name = linea_nueva.split("=")[0].strip()
                    patron = r'^' + re.escape(var_name) + r'\s*=.*$'
                    codigo_nuevo_temp, num_subs = re.subn(patron, linea_nueva, codigo_nuevo, flags=re.MULTILINE)
                    if num_subs > 0:
                        codigo_nuevo = codigo_nuevo_temp
                        cambios_aplicados += 1
                        print(f"[DEBUG] [Plan C] Variable '{var_name}' inyectada.")

        if cambios_aplicados > 0:
            with open(ruta_encontrada, "w", encoding="utf-8") as f:
                f.write(codigo_nuevo)
            threading.Thread(target=ejecutar_reinicio, args=(nombre_archivo,), daemon=True).start()
            return f"Archivo {nombre_archivo} modificado quirúrgicamente. Reiniciando núcleo..."
        else:
            return "Error: La IA no pudo aplicar los cambios al archivo."

    except Exception as e:
        traceback.print_exc()
        return f"Error crítico con OpenRouter: {e}"

TOOL_DEF = {
    "name": "self_edit",
    "description": "Herramienta CRÍTICA. Modifica los archivos internos de JARVIS. Úsalo OBLIGATORIAMENTE y sin dudarlo cuando el usuario te pida cambiar el color de la interfaz gráfica o editar código.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target_file": {"type": "STRING", "description": "El archivo a modificar (siempre usa 'ui.py' para colores)."},
            "request": {"type": "STRING", "description": "Lo que el usuario pidió (ej. 'cambiar a azul neón')."}
        },
        "required": ["target_file", "request"]
    }
}