import os
import json
from pathlib import Path

# Definimos la ruta de la "Corteza Cerebral"
BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_FILE = BASE_DIR / "config" / "long_term_memory.json"

def memory_manager(parameters: dict) -> str:
    action = parameters.get("action", "").lower()
    fact = parameters.get("fact", "").strip()
    
    # Cargar los recuerdos actuales
    memory = {"hechos": []}
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memory = json.load(f)
        except Exception:
            pass
    if not isinstance(memory, dict):
        memory = {"hechos": []}
    if not isinstance(memory.get("hechos"), list):
        memory["hechos"] = []
            
    if action == "save":
        if not fact: 
            return "Error: No me enviaste ningún dato para guardar."
            
        if fact not in memory["hechos"]:
            memory["hechos"].append(fact)
            
            # Guardar en el disco duro
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(memory, f, indent=4, ensure_ascii=False)
                
            return f"🧠 Hecho aprendido y guardado en mi memoria permanente: '{fact}'."
        return "Ese dato ya estaba registrado en mi memoria, señor."
        
    elif action == "read":
        if not memory["hechos"]: 
            return "Mi memoria a largo plazo está en blanco."
        datos = "\n- ".join(memory["hechos"])
        return f"Esto es lo que he aprendido sobre el usuario y mis configuraciones operativas:\n- {datos}"
        
    elif action == "clear":
        if MEMORY_FILE.exists(): 
            os.remove(MEMORY_FILE)
        return "Memoria borrada por completo. He olvidado todo sobre el usuario."

    return "Acción no reconocida."

# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "memory_manager",
    "description": "El Hipocampo de JARVIS (Memoria a largo plazo). Úsalo CADA VEZ que el usuario te cuente algo sobre él, una preferencia, un gusto, o te dé una instrucción de cómo quiere que te comportes de ahora en adelante. También puedes usarlo con la acción 'read' para recordar qué sabes del usuario.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "'save' (guardar nuevo dato), 'read' (leer la memoria), o 'clear' (borrar todo)."},
            "fact": {"type": "STRING", "description": "El dato concreto que vas a aprender (solo si la acción es 'save'). Ejemplo: 'Al usuario le gusta programar en Python'."}
        },
        "required": ["action"]
    }
}