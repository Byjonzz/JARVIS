import os
import requests
import traceback
import json
import re

# ⏱️ Límite que respeta main.py: generar un parche con el modelo razonador de
# OpenRouter tarda minutos (el default de 30s cancelaba la espera siempre).
TOOL_TIMEOUT = 300
# 🚀 main.py la ejecuta en segundo plano y anuncia por voz cuando termina de verdad.
TOOL_BACKGROUND = True

# El reinicio ya NO lo hace esta herramienta: antes un temporizador ciego de 6-12s
# mataba el proceso a mitad del anuncio por voz y se perdía la conversación. Ahora
# se devuelve el marcador MARCA_REINICIO y main.py reinicia cuando I.R.I.S. TERMINA
# de hablar, guardando el asa de la sesión para retomar el contexto tras reiniciar.
MARCA_REINICIO = "[REINICIO_REQUERIDO]"

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
        # Mismo modelo del auto-programador, cambiable con OPENROUTER_MODEL en .env
        modelo = (os.getenv("OPENROUTER_MODEL") or "nvidia/nemotron-3-ultra-550b-a55b:free").strip()
        payload = {
            "model": modelo,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            # Los modelos razonadores devuelven su "pensamiento" antes del parche;
            # esto lo excluye para que el formato [BUSCAR]/[REEMPLAZAR] llegue limpio.
            "reasoning": {"exclude": True}
        }

        print(f"[DEBUG] Generando parche con OpenRouter ({modelo})...")
        response = requests.post(url, headers=headers, json=payload, timeout=280)
        if response.status_code != 200:
            return f"Error de OpenRouter (HTTP {response.status_code}): {response.text[:300]}"

        datos = response.json()
        if "choices" not in datos or not datos["choices"]:
            return f"OpenRouter respondió sin contenido: {str(datos)[:300]}"
        texto_completo = datos["choices"][0]["message"]["content"] or ""
                    
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
            # El ÚLTIMO bloque: si el modelo razona en voz alta, el definitivo va al final
            bloques_codigo = re.findall(r'```(?:python|py)?[ \t]*\r?\n(.*?)```', texto_completo, re.DOTALL)
            texto_a_procesar = bloques_codigo[-1] if bloques_codigo else texto_completo
            
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
            # 🛡️ Validar ANTES de escribir: un parche con error de sintaxis haría
            # desaparecer la herramienta del catálogo al recargarla, justo mientras
            # el aviso por voz dice "ya se puede usar".
            if ruta_encontrada.endswith(".py"):
                try:
                    compile(codigo_nuevo, ruta_encontrada, "exec")
                except SyntaxError as e:
                    return (f"Error: el parche generado para {nombre_archivo} no compila "
                            f"(línea {e.lineno}: {e.msg}). No toqué el archivo; el original sigue intacto.")

            with open(ruta_encontrada, "w", encoding="utf-8") as f:
                f.write(codigo_nuevo)

            # Las herramientas de actions/ se recargan EN CALIENTE (main.py vuelve a
            # descubrirlas al terminar esta tarea): no hace falta reiniciar nada.
            # Solo los archivos del núcleo (ui.py, main.py...) exigen reinicio.
            en_actions = os.path.basename(os.path.dirname(os.path.abspath(ruta_encontrada))) == "actions"
            if en_actions:
                return (f"Archivo {nombre_archivo} modificado quirúrgicamente. La herramienta "
                        "se recargará sola: ya se puede usar, sin reiniciar nada.")
            return (f"{MARCA_REINICIO} Archivo del núcleo {nombre_archivo} modificado quirúrgicamente. "
                    "La interfaz se reiniciará sola en cuanto termine este aviso y la conversación "
                    "continuará donde estaba.")
        else:
            return "Error: La IA no pudo aplicar los cambios al archivo."

    except Exception as e:
        traceback.print_exc()
        return f"Error crítico con OpenRouter: {e}"

TOOL_DEF = {
    "name": "self_edit",
    "description": (
        "Herramienta CRÍTICA. EDITA archivos y herramientas que YA EXISTEN dentro de JARVIS: "
        "úsala sin dudar cuando el usuario pida arreglar, corregir, mejorar o cambiar una "
        "herramienta ya creada (archivos de actions/) o la interfaz (colores → 'ui.py'). "
        "Si lo que pide es crear una herramienta NUEVA que no existe, NO uses esta: usa "
        "'auto_programmer'. Tarda hasta 3 minutos: avisa al usuario de que trabajarás en "
        "ello y NO la llames dos veces por la misma petición."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target_file": {"type": "STRING", "description": "El archivo a modificar (ej. 'os_control.py' para esa herramienta, 'ui.py' para colores)."},
            "request": {"type": "STRING", "description": "Lo que el usuario pidió (ej. 'arregla el control de volumen', 'cambiar a azul neón')."}
        },
        "required": ["target_file", "request"]
    }
}