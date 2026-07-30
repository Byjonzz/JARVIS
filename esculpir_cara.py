# -*- coding: utf-8 -*-
"""Escultor de la cabeza holografica de I.R.I.S.

Modela una cabeza humana con campos de distancia (SDF), muestrea su superficie
como nube de puntos, calcula pesos de mandibula/labio (para hablar), brillos
(silueta y rasgos) y la red de lineas 'plexus' (vecinos cercanos), y hornea todo
en assets/cara_datos.js para el HUD. Genera previews PNG para iterar la forma.
"""
import base64
import sys
import numpy as np
from scipy.spatial import cKDTree
from PIL import Image, ImageDraw

# Rutas relativas a la raíz del proyecto (ejecutar desde ahí):
#   .venv\Scripts\python.exe esculpir_cara.py            → hornea assets/cara_datos.js
#   .venv\Scripts\python.exe esculpir_cara.py --preview  → solo genera los PNG de vista previa
RUTA_SALIDA = "assets/cara_datos.js"
RUTA_PREVIEW = "."

rng = np.random.default_rng(7)

# ---------- primitivas SDF (vectorizadas: p es (N,3)) ----------
def sd_elipsoide(p, c, r):
    q = (p - c) / r
    k0 = np.linalg.norm(q, axis=1)
    k1 = np.linalg.norm(q / r, axis=1)
    return np.where(k1 > 1e-9, k0 * (k0 - 1.0) / np.maximum(k1, 1e-9), -np.min(r))

def sd_esfera(p, c, r):
    return np.linalg.norm(p - c, axis=1) - r

def sd_capsula(p, a, b, r):
    a = np.asarray(a, float); b = np.asarray(b, float)
    pa = p - a; ba = b - a
    h = np.clip((pa @ ba) / (ba @ ba), 0, 1)
    return np.linalg.norm(pa - np.outer(h, ba), axis=1) - r

def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)

def smax(a, b, k):        # interseccion suave con -b => resta
    return -smin(-a, -b, k)

# ---------- LA CABEZA ----------
def cabeza(p):
    # craneo (bien redondo por detras, como la referencia)
    d = sd_elipsoide(p, (0, 3.2, -0.8), (6.9, 8.2, 7.6))
    # pomulos
    d = smin(d, sd_esfera(p, (4.3, 1.2, 3.4), 1.9), 1.6)
    d = smin(d, sd_esfera(p, (-4.3, 1.2, 3.4), 1.9), 1.6)
    # arco superciliar (cejas oseas)
    d = smin(d, sd_capsula(p, (-3.3, 3.9, 5.1), (3.3, 3.9, 5.1), 1.30), 1.2)
    # mandibula y menton
    d = smin(d, sd_capsula(p, (4.8, 0.2, -0.4), (1.5, -6.4, 3.2), 1.65), 1.6)
    d = smin(d, sd_capsula(p, (-4.8, 0.2, -0.4), (-1.5, -6.4, 3.2), 1.65), 1.6)
    d = smin(d, sd_esfera(p, (0, -6.7, 3.8), 1.85), 1.5)
    # maxilar (base de la boca)
    d = smin(d, sd_esfera(p, (0, -2.9, 4.5), 2.0), 1.8)
    # nariz: caballete, punta y aletas
    d = smin(d, sd_capsula(p, (0, 3.4, 5.8), (0, -0.7, 7.8), 0.72), 1.0)
    d = smin(d, sd_esfera(p, (0, -1.1, 8.0), 0.98), 0.8)
    d = smin(d, sd_esfera(p, (0.95, -1.55, 7.0), 0.60), 0.6)
    d = smin(d, sd_esfera(p, (-0.95, -1.55, 7.0), 0.60), 0.6)
    # labios
    d = smin(d, sd_capsula(p, (-1.85, -3.10, 6.55), (1.85, -3.10, 6.55), 0.60), 0.7)
    d = smin(d, sd_capsula(p, (-1.55, -4.15, 6.60), (1.55, -4.15, 6.60), 0.70), 0.7)
    # cuello
    d = smin(d, sd_capsula(p, (0, -6.3, -1.6), (0, -12.5, -2.4), 2.85), 2.4)
    # orejas
    d = smin(d, sd_elipsoide(p, (7.0, 1.4, -1.6), (0.7, 2.0, 1.4)), 0.9)
    d = smin(d, sd_elipsoide(p, (-7.0, 1.4, -1.6), (0.7, 2.0, 1.4)), 0.9)
    # cuencas de los ojos (se restan) y globos oculares (se suman)
    d = smax(d, -sd_esfera(p, (2.85, 2.5, 5.95), 1.72), 0.9)
    d = smax(d, -sd_esfera(p, (-2.85, 2.5, 5.95), 1.72), 0.9)
    d = smin(d, sd_esfera(p, (2.85, 2.45, 4.95), 1.42), 0.5)
    d = smin(d, sd_esfera(p, (-2.85, 2.45, 4.95), 1.42), 0.5)
    # surco entre labios (linea de la boca)
    d = smax(d, -sd_capsula(p, (-1.95, -3.62, 7.15), (1.95, -3.62, 7.15), 0.24), 0.35)
    return d

def gradiente(p, h=0.02):
    g = np.zeros_like(p)
    for i in range(3):
        e = np.zeros(3); e[i] = h
        g[:, i] = (cabeza(p + e) - cabeza(p - e)) / (2 * h)
    return g

# ---------- muestreo de la superficie ----------
def muestrear(n_obj=9000, lote=60000, max_iter=40):
    puntos = []
    for _ in range(max_iter):
        p = rng.uniform((-9.5, -12.8, -9.5), (9.5, 12.5, 10.5), (lote, 3))
        d = cabeza(p)
        cerca = np.abs(d) < 2.2
        p = p[cerca]
        for _ in range(5):                     # proyeccion de Newton a la superficie
            d = cabeza(p)
            g = gradiente(p)
            gn = np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-6)
            p = p - g / gn * d[:, None] * 0.9
        d = cabeza(p)
        p = p[np.abs(d) < 0.03]
        puntos.append(p)
        if sum(len(q) for q in puntos) > n_obj * 3:
            break
    p = np.concatenate(puntos)
    # adelgazar para densidad uniforme
    arbol = cKDTree(p)
    vivos = np.ones(len(p), bool)
    dmin = 0.30
    for i in np.argsort(rng.random(len(p))):
        if not vivos[i]:
            continue
        for j in arbol.query_ball_point(p[i], dmin):
            if j != i:
                vivos[j] = False
    p = p[vivos]
    if len(p) > n_obj:
        p = p[rng.choice(len(p), n_obj, replace=False)]
    return p

def pesos_y_brillo(p):
    n = gradiente(p)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-6)
    x, y, z = p[:, 0], p[:, 1], p[:, 2]

    # ---- peso de habla: labio inferior + mandibula (bisagra en la oreja) ----
    d_labio_inf = np.linalg.norm(p - (0, -4.15, 6.6), axis=1)
    labio_inf = np.clip(1.6 - d_labio_inf * 0.55, 0, 1)
    frente = np.clip((z + 1.5) / 6.0, 0, 1)          # solo la parte delantera cae
    mandibula = np.clip((-1.2 - y) / 2.2, 0, 1) * np.clip((y + 8.2) / 2.0, 0, 1) * frente
    w = np.clip(np.maximum(labio_inf, mandibula * 0.85), 0, 1)
    d_labio_sup = np.linalg.norm(p - (0, -3.05, 6.55), axis=1)
    w = np.where((d_labio_sup < 1.1) & (y > -3.6), 0.06, w)   # labio superior casi fijo

    # ---- brillo: silueta frontal + rasgos ----
    rim = (1 - np.abs(n[:, 2])) ** 1.6                # borde visto de frente
    b = 0.30 + 0.55 * rim
    rasgos = np.minimum.reduce([
        np.abs(sd_capsula(p, (-1.85, -3.10, 6.55), (1.85, -3.10, 6.55), 0.60)),
        np.abs(sd_capsula(p, (-1.55, -4.15, 6.60), (1.55, -4.15, 6.60), 0.70)),
        np.abs(sd_esfera(p, (2.85, 2.45, 4.95), 1.42)),
        np.abs(sd_esfera(p, (-2.85, 2.45, 4.95), 1.42)),
        np.abs(sd_esfera(p, (0, -1.1, 8.0), 0.98)),
        np.abs(sd_capsula(p, (-3.3, 3.9, 5.1), (3.3, 3.9, 5.1), 1.30)),
    ])
    b += np.clip(0.62 - rasgos * 1.35, 0, 0.42)
    b += np.where(y < -9.5, -0.16, 0) + np.where(y < -11.0, -0.10, 0)               # el cuello se desvanece
    return np.clip(w, 0, 1), np.clip(b, 0.05, 1.4), n

def red_plexus(p, k=3, dmax=1.45, tope=13000):
    arbol = cKDTree(p)
    dist, idx = arbol.query(p, k=k + 1)
    aristas = set()
    for i in range(len(p)):
        for j in range(1, k + 1):
            if dist[i, j] < dmax:
                a, b2 = sorted((i, idx[i, j]))
                aristas.add((a, b2))
    aristas = np.array(sorted(aristas), dtype=np.uint16)
    if len(aristas) > tope:
        aristas = aristas[rng.choice(len(aristas), tope, replace=False)]
    return aristas

# ---------- preview PNG ----------
def preview(p, b, aristas, nombre, yaw):
    cy, sy = np.cos(yaw), np.sin(yaw)
    R = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    q = p @ R.T
    ancho, alto = 640, 760
    esc = 24.0
    xs = (q[:, 0] * esc + ancho / 2).astype(int)
    ys = (alto / 2 - q[:, 1] * esc - 40).astype(int)
    orden = np.argsort(q[:, 2])
    img = Image.new("RGB", (ancho, alto), (3, 6, 10))
    dib = ImageDraw.Draw(img, "RGBA")
    if aristas is not None:
        for a, c in aristas[:: max(1, len(aristas) // 5000)]:
            dib.line([(xs[a], ys[a]), (xs[c], ys[c])], fill=(0, 170, 210, 38), width=1)
    for i in orden:
        v = float(np.clip(b[i], 0, 1.3))
        prof = float(np.clip((q[i, 2] + 10) / 20, 0.25, 1))
        col = (int(30 * v * prof), int(215 * v * prof), int(255 * v * prof), 220)
        dib.ellipse([xs[i] - 1, ys[i] - 1, xs[i] + 1, ys[i] + 1], fill=col)
    img.save(f"{RUTA_PREVIEW}\\{nombre}.png")

# ---------- hornear ----------
def hornear(p, w, b, aristas):
    b64 = lambda a: base64.b64encode(a.tobytes()).decode()
    contenido = (
        "// Generado por esculpir_cara.py — cabeza humana SDF muestreada (no editar a mano)\n"
        "window.CARA_DATOS = {\n"
        f"  n: {len(p)},\n"
        f"  p: \"{b64(p.astype(np.float32))}\",\n"
        f"  w: \"{b64((w * 255).astype(np.uint8))}\",\n"
        f"  b: \"{b64((np.clip(b, 0, 1.4) / 1.4 * 255).astype(np.uint8))}\",\n"
        f"  e: \"{b64(aristas.astype(np.uint16))}\",\n"
        "};\n"
    )
    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        f.write(contenido)
    print(f"horneado: {len(p)} puntos, {len(aristas)} aristas -> {RUTA_SALIDA} ({len(contenido)//1024} KB)")

if __name__ == "__main__":
    solo_preview = "--preview" in sys.argv
    print("muestreando superficie...")
    p = muestrear()
    print(f"  {len(p)} puntos")
    w, b, n = pesos_y_brillo(p)
    print("tejiendo la red plexus...")
    aristas = red_plexus(p)
    print(f"  {len(aristas)} aristas")
    preview(p, b, aristas, "cara_frente", 0.0)
    preview(p, b, aristas, "cara_tres_cuartos", 0.45)
    preview(p, b, aristas, "cara_perfil", 1.25)
    print("previews listos")
    if not solo_preview:
        hornear(p, w, b, aristas)
