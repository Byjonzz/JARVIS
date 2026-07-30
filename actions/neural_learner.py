"""
🧠 neural_learner — El cerebro que aprende de I.R.I.S.

Red neuronal REAL (perceptrón multicapa con retropropagación, escrito con numpy,
sin frameworks externos) que aprende la relación entre LO QUE DICE EL USUARIO y
LA HERRAMIENTA que se ejecutó. Cada orden de voz es un ejemplo de entrenamiento:
el sistema mejora automáticamente con el uso.

Archivos que genera:
- config/neural_dataset.jsonl  → memoria de ejemplos (frase → herramienta)
- config/neural_pesos.npz      → matrices de pesos W1, b1, W2, b2
- config/neural_meta.json      → clases conocidas, precisión y contadores
"""
import json
import re
import threading
import time
import unicodedata
import zlib
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
RUTA_DATASET = BASE_DIR / "config" / "neural_dataset.jsonl"
RUTA_PESOS = BASE_DIR / "config" / "neural_pesos.npz"
RUTA_META = BASE_DIR / "config" / "neural_meta.json"

DIM_ENTRADA = 512   # dimensión del hashing de palabras
DIM_OCULTA = 64     # neuronas de la capa oculta

_LOCK = threading.Lock()
_MODELO = None      # se carga de disco la primera vez que se necesita


# ---------- Procesamiento de texto ----------

def _normalizar(texto: str) -> list:
    texto = (texto or "").lower()
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9]+", texto)


def _vectorizar(texto: str) -> np.ndarray:
    """Bolsa de palabras con 'feature hashing' estable (unigramas + bigramas).
    Se usa crc32 y no hash() porque hash() cambia en cada reinicio de Python."""
    x = np.zeros(DIM_ENTRADA, dtype=np.float64)
    tokens = _normalizar(texto)
    for t in tokens:
        x[zlib.crc32(t.encode("utf-8")) % DIM_ENTRADA] += 1.0
    # Los bigramas aportan contexto pero con menos peso que las palabras sueltas
    for a, b in zip(tokens, tokens[1:]):
        x[zlib.crc32(f"{a}_{b}".encode("utf-8")) % DIM_ENTRADA] += 0.5
    norma = np.linalg.norm(x)
    return x / norma if norma > 0 else x


# ---------- La red neuronal ----------

class RedNeuronal:
    """Perceptrón multicapa: entrada 256 → capa oculta 64 (tanh) → softmax de herramientas."""

    def __init__(self, clases):
        rng = np.random.default_rng(42)
        self.clases = list(clases)
        self.W1 = rng.normal(0, 0.2, (DIM_ENTRADA, DIM_OCULTA))
        self.b1 = np.zeros(DIM_OCULTA)
        self.W2 = rng.normal(0, 0.1, (DIM_OCULTA, max(len(self.clases), 1)))
        self.b2 = np.zeros(max(len(self.clases), 1))
        self.precision = 0.0
        self.entrenamientos = 0

    def _adelante(self, x):
        h = np.tanh(x @ self.W1 + self.b1)
        logits = h @ self.W2 + self.b2
        logits = logits - logits.max()
        e = np.exp(logits)
        return h, e / e.sum()

    def agregar_clase(self, clase):
        rng = np.random.default_rng(len(self.clases) + 7)
        self.clases.append(clase)
        if self.W2.shape[1] < len(self.clases):
            col = rng.normal(0, 0.1, (DIM_OCULTA, 1))
            self.W2 = np.hstack([self.W2, col])
            self.b2 = np.append(self.b2, 0.0)

    def entrenar(self, ejemplos, epocas=5, lr=0.08):
        """Descenso de gradiente estocástico con retropropagación."""
        if not ejemplos:
            return 0.0
        for texto, clase in ejemplos:
            if clase not in self.clases:
                self.agregar_clase(clase)

        indices = np.arange(len(ejemplos))
        rng = np.random.default_rng(self.entrenamientos + 1)
        for _ in range(epocas):
            rng.shuffle(indices)
            for i in indices:
                texto, clase = ejemplos[i]
                y = self.clases.index(clase)
                x = _vectorizar(texto)
                h, p = self._adelante(x)

                # Gradientes (softmax + entropía cruzada)
                dlogits = p.copy()
                dlogits[y] -= 1.0
                dW2 = np.outer(h, dlogits)
                dh = self.W2 @ dlogits
                dpre = dh * (1.0 - h * h)  # derivada de tanh
                dW1 = np.outer(x, dpre)

                self.W2 -= lr * dW2
                self.b2 -= lr * dlogits
                self.W1 -= lr * dW1
                self.b1 -= lr * dpre

        self.entrenamientos += 1
        aciertos = sum(1 for t, c in ejemplos if self.predecir(t)[0] == c)
        self.precision = aciertos / len(ejemplos)
        return self.precision

    def predecir(self, texto):
        if not self.clases:
            return ("", 0.0)
        _, p = self._adelante(_vectorizar(texto))
        i = int(np.argmax(p[:len(self.clases)]))
        return self.clases[i], float(p[i])


# ---------- Persistencia ----------

def _guardar(modelo):
    RUTA_PESOS.parent.mkdir(parents=True, exist_ok=True)
    np.savez(RUTA_PESOS, W1=modelo.W1, b1=modelo.b1, W2=modelo.W2, b2=modelo.b2)
    meta = {
        "clases": modelo.clases,
        "precision": modelo.precision,
        "entrenamientos": modelo.entrenamientos,
        "dim_entrada": DIM_ENTRADA,
        "dim_oculta": DIM_OCULTA,
    }
    RUTA_META.write_text(json.dumps(meta, indent=4, ensure_ascii=False), encoding="utf-8")


def _cargar():
    global _MODELO
    if _MODELO is not None:
        return _MODELO
    try:
        if RUTA_PESOS.exists() and RUTA_META.exists():
            meta = json.loads(RUTA_META.read_text(encoding="utf-8"))
            if meta.get("dim_entrada") == DIM_ENTRADA and meta.get("dim_oculta") == DIM_OCULTA:
                m = RedNeuronal(meta.get("clases", []))
                datos = np.load(RUTA_PESOS)
                m.W1, m.b1 = datos["W1"], datos["b1"]
                m.W2, m.b2 = datos["W2"], datos["b2"]
                m.precision = float(meta.get("precision", 0.0))
                m.entrenamientos = int(meta.get("entrenamientos", 0))
                _MODELO = m
    except Exception:
        _MODELO = None
    return _MODELO


def _leer_dataset(maximo=None):
    ejemplos = []
    if RUTA_DATASET.exists():
        try:
            with open(RUTA_DATASET, "r", encoding="utf-8") as f:
                for linea in f:
                    linea = linea.strip()
                    if not linea:
                        continue
                    try:
                        d = json.loads(linea)
                        if d.get("texto") and d.get("herramienta"):
                            ejemplos.append((d["texto"], d["herramienta"]))
                    except Exception:
                        continue
        except Exception:
            pass
    if maximo and len(ejemplos) > maximo:
        ejemplos = ejemplos[-maximo:]
    return ejemplos


# ---------- API usada por main.py (aprendizaje automático en segundo plano) ----------

def registrar_interaccion(texto_usuario: str, herramienta: str) -> str:
    """Guarda el ejemplo (frase → herramienta) y reentrena la red al instante."""
    global _MODELO
    texto_usuario = (texto_usuario or "").strip()
    herramienta = (herramienta or "").strip()
    if not texto_usuario or not herramienta:
        return "Red neuronal: turno sin transcripción del usuario, no hay nada que aprender."

    with _LOCK:
        RUTA_DATASET.parent.mkdir(parents=True, exist_ok=True)
        with open(RUTA_DATASET, "a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"texto": texto_usuario, "herramienta": herramienta,
                 "ts": time.strftime("%Y-%m-%d %H:%M:%S")},
                ensure_ascii=False) + "\n")

        modelo = _cargar()
        if modelo is None:
            modelo = RedNeuronal([herramienta])
            _MODELO = modelo

        # Reentrenamos con la memoria reciente (repaso) + el ejemplo nuevo
        ejemplos = _leer_dataset(maximo=300)
        precision = modelo.entrenar(ejemplos, epocas=10)
        _guardar(modelo)
        total = len(_leer_dataset())

    return (f"Aprendido: '{texto_usuario[:45]}' → {herramienta} | "
            f"{total} ejemplos, {len(modelo.clases)} herramientas, precisión {precision:.0%}")


def predecir(texto: str):
    with _LOCK:
        modelo = _cargar()
    if modelo is None or not modelo.clases:
        return ("", 0.0)
    return modelo.predecir(texto)


# ---------- Herramienta expuesta a Gemini ----------

def neural_learner(parameters: dict) -> str:
    global _MODELO
    action = (parameters.get("action") or "stats").lower()
    texto = (parameters.get("text") or "").strip()

    if action == "predict":
        if not texto:
            return "Error: envía la frase a evaluar en el parámetro 'text'."
        clase, prob = predecir(texto)
        if not clase:
            return "Mi red neuronal aún está en blanco: todavía no he aprendido ninguna orden."
        return (f"Mi red neuronal predice que '{texto}' corresponde a la herramienta "
                f"'{clase}' con {prob:.0%} de confianza.")

    elif action == "retrain":
        ejemplos = _leer_dataset()
        if not ejemplos:
            return "No hay ejemplos guardados todavía; ejecuta órdenes por voz y volveré a intentarlo."
        with _LOCK:
            _MODELO = RedNeuronal(sorted({c for _, c in ejemplos}))
            precision = _MODELO.entrenar(ejemplos, epocas=30)
            _guardar(_MODELO)
        return f"Reentrenamiento completo: {len(ejemplos)} ejemplos, precisión final {precision:.0%}."

    elif action == "stats":
        ejemplos = _leer_dataset()
        with _LOCK:
            modelo = _cargar()
        if modelo is None or not ejemplos:
            return ("Aún no he aprendido nada: ejecuta órdenes por voz y mi red neuronal "
                    "comenzará a entrenarse sola con cada una.")
        conteo = {}
        for _, c in ejemplos:
            conteo[c] = conteo.get(c, 0) + 1
        detalle = ", ".join(f"{c} ({n})" for c, n in sorted(conteo.items(), key=lambda kv: -kv[1]))
        return (f"He aprendido de {len(ejemplos)} órdenes reales. Reconozco {len(modelo.clases)} "
                f"herramientas: {detalle}. Precisión del último entrenamiento: {modelo.precision:.0%}. "
                f"Arquitectura: {DIM_ENTRADA} entradas → {DIM_OCULTA} neuronas ocultas → "
                f"{len(modelo.clases)} salidas.")

    return "Acción no reconocida. Usa 'predict', 'stats' o 'retrain'."


# 🟢 EL MANUAL AUTODESCUBRIBLE
TOOL_DEF = {
    "name": "neural_learner",
    "description": (
        "El cerebro de aprendizaje de I.R.I.S.: una red neuronal local que entrena sola con cada "
        "orden ejecutada. Úsalo con 'stats' cuando el usuario pregunte qué o cuánto has aprendido, "
        "'predict' para decir qué herramienta usarías ante una frase, y 'retrain' si pide reentrenar."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "'stats' (resumen de lo aprendido), 'predict' (predecir herramienta para una frase) o 'retrain' (reentrenar desde cero)."},
            "text": {"type": "STRING", "description": "La frase a evaluar (solo para 'predict')."}
        },
        "required": ["action"]
    }
}
