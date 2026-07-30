# -*- coding: utf-8 -*-
"""Escultor de la cabeza holografica de I.R.I.S.

Construye la cabeza a partir de la MALLA FACIAL CANONICA de MediaPipe
(assets/canonical_face_model.obj, Apache-2.0): 468 vertices y 898 triangulos de
una cara humana promedio real. No son datos biometricos de ninguna persona: es la
geometria facial media que la industria usa para colocar filtros.

Por que asi y no con formas analiticas: una cara real no se puede componer con
esferas y capsulas —la version anterior salia deforme por eso—. Aqui la geometria
del rostro es real y solo se anaden craneo, orejas y cuello, que la malla canonica
no cubre.

Salidas:
  assets/cara_datos.js  — nube de puntos, pesos de mandibula, brillos y aristas
  *.png                 — vistas previas para iterar la forma

Uso (desde la raiz del proyecto):
  .venv\\Scripts\\python.exe esculpir_cara.py            → hornea los datos
  .venv\\Scripts\\python.exe esculpir_cara.py --preview  → solo las vistas previas
"""
import base64
import sys
import numpy as np
from scipy.spatial import cKDTree
from PIL import Image, ImageDraw

RUTA_OBJ = "assets/canonical_face_model.obj"
RUTA_SALIDA = "assets/cara_datos.js"
RUTA_PREVIEW = "."

rng = np.random.default_rng(7)

# Bisagra real de la mandibula (articulacion temporomandibular, junto a las orejas)
BISAGRA_Y, BISAGRA_Z = 0.67, -2.44
# La boca: entre el labio superior interno (13) y el inferior interno (14)
LINEA_BOCA_Y = -4.25


# ---------- carga de la malla canonica ----------
def cargar_obj(ruta):
    V, F = [], []
    for linea in open(ruta, encoding="utf-8"):
        if linea.startswith("v "):
            V.append([float(x) for x in linea.split()[1:4]])
        elif linea.startswith("f "):
            F.append([int(t.split("/")[0]) - 1 for t in linea.split()[1:4]])
    return np.array(V, float), np.array(F, int)


def aristas_de_caras(F):
    e = set()
    for a, b, c in F:
        for i, j in ((a, b), (b, c), (c, a)):
            e.add((min(i, j), max(i, j)))
    return np.array(sorted(e), dtype=np.int32)


def muestrear_triangulos(V, F, n):
    """Puntos repartidos por area sobre la superficie real de la cara."""
    A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    areas = 0.5 * np.linalg.norm(np.cross(B - A, C - A), axis=1)
    idx = rng.choice(len(F), n, p=areas / areas.sum())
    u = rng.random((n, 1)); v = rng.random((n, 1))
    fuera = (u + v) > 1
    u[fuera] = 1 - u[fuera]; v[fuera] = 1 - v[fuera]
    return A[idx] + u * (B[idx] - A[idx]) + v * (C[idx] - A[idx])


# ---------- craneo, orejas y cuello (lo que la malla facial no trae) ----------
def craneo(V_cara, n):
    """Elipsoide detras de la cara; se descartan los puntos que la atravesarian."""
    centro = np.array([0.0, 1.2, 0.6])
    radios = np.array([7.9, 9.3, 8.4])
    arbol = cKDTree(V_cara)
    salida = []
    while sum(len(s) for s in salida) < n:
        m = n * 3
        th = rng.random(m) * 2 * np.pi
        cph = rng.random(m) * 2 - 1
        sph = np.sqrt(1 - cph ** 2)
        p = centro + np.stack([radios[0] * sph * np.cos(th),
                               radios[1] * cph,
                               radios[2] * sph * np.sin(th)], 1)
        d, i = arbol.query(p)
        # fuera si esta por delante de la cara (la atravesaria) o pegado a ella
        delante = p[:, 2] > V_cara[i][:, 2] + 0.25
        salida.append(p[~delante & (d > 0.9)])
    return np.concatenate(salida)[:n]


def orejas(n):
    p = []
    for lado in (-1, 1):
        c = np.array([lado * 7.5, 0.9, -2.2])
        th = rng.random(n // 2) * 2 * np.pi
        cph = rng.random(n // 2) * 2 - 1
        sph = np.sqrt(1 - cph ** 2)
        q = c + np.stack([0.55 * sph * np.cos(th), 2.1 * cph, 1.5 * sph * np.sin(th)], 1)
        p.append(q)
    return np.concatenate(p)


def cuello(n):
    a = np.array([0.0, -7.5, 0.4]); b = np.array([0.0, -14.5, -0.6])
    t = rng.random(n)[:, None]
    eje = a + t * (b - a)
    r = 3.15 - 0.35 * t[:, 0]
    th = rng.random(n) * 2 * np.pi
    return eje + np.stack([r * np.cos(th), np.zeros(n), r * np.sin(th) * 1.05], 1)


def ojos(n):
    """Globos oculares: la malla canonica solo trae el contorno de los parpados."""
    p = []
    for lado in (-1, 1):
        c = np.array([lado * 3.15, 2.75, 2.55])
        th = rng.random(n // 2) * 2 * np.pi
        cph = rng.random(n // 2) * 2 - 1
        sph = np.sqrt(1 - cph ** 2)
        q = c + 1.30 * np.stack([sph * np.cos(th), cph, sph * np.sin(th)], 1)
        p.append(q[q[:, 2] > c[2] - 0.2])      # solo la mitad visible
    return np.concatenate(p)


# ---------- pesos de habla y brillo ----------
def peso_mandibula(p, es_cuello):
    """1 en todo lo que cuelga de la mandibula, 0 del labio superior hacia arriba."""
    y = p[:, 1]
    t = np.clip((LINEA_BOCA_Y - y) / 0.75, 0, 1)
    w = t * t * (3 - 2 * t)                    # transicion suave justo en la boca
    w[es_cuello] = 0.0                         # el cuello no se mueve
    return w


def brillo(p, V, idx_rasgos, es_nodo, es_ojo, es_cuello):
    b = np.full(len(p), 0.22)
    # realce de rasgos: cerca de labios, ojos, nariz y cejas de la malla real
    arbol = cKDTree(V[idx_rasgos])
    d, _ = arbol.query(p)
    b += np.clip(0.75 - d * 0.85, 0, 0.62)
    # silueta: los puntos mas laterales o mas altos destacan
    r = np.linalg.norm(p[:, [0, 1]] - np.array([0, 0.5]), axis=1)
    b += np.clip((r - 6.6) * 0.16, 0, 0.30)
    b[es_nodo] += 0.42                         # los vertices de la malla son los nodos
    b[es_ojo] = 1.15                           # iris encendido
    b[es_cuello] *= 0.55                       # el cuello se desvanece
    b -= np.clip((-9.5 - p[:, 1]) * 0.10, 0, 0.18)
    return np.clip(b, 0.05, 1.4)


# ---------- vista previa ----------
def preview(p, b, aristas, nombre, yaw, ap=0.0, w=None, bisagra=(BISAGRA_Y, BISAGRA_Z)):
    if ap > 0 and w is not None:                # simular la boca abierta
        p = p.copy()
        by, bz = bisagra
        dy = p[:, 1] - by; dz = p[:, 2] - bz
        ang = w * ap * 0.34
        p[:, 1] = by + dy * np.cos(ang) - dz * np.sin(ang)
        p[:, 2] = bz + dy * np.sin(ang) + dz * np.cos(ang)
    cy, sy = np.cos(yaw), np.sin(yaw)
    R = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    q = p @ R.T
    ancho, alto, esc = 640, 780, 25.0
    xs = (q[:, 0] * esc + ancho / 2).astype(int)
    ys = (alto / 2 - q[:, 1] * esc - 30).astype(int)
    img = Image.new("RGB", (ancho, alto), (3, 6, 10))
    dib = ImageDraw.Draw(img, "RGBA")
    for a1, a2 in aristas:
        prof = np.clip((q[a1, 2] + 10) / 20, 0.15, 1)
        dib.line([(xs[a1], ys[a1]), (xs[a2], ys[a2])],
                 fill=(0, int(150 * prof), int(190 * prof), 70), width=1)
    for i in np.argsort(q[:, 2]):
        v = float(np.clip(b[i], 0, 1.3))
        prof = float(np.clip((q[i, 2] + 10) / 20, 0.25, 1))
        r = 1 if v < 0.7 else 2
        dib.ellipse([xs[i] - r, ys[i] - r, xs[i] + r, ys[i] + r],
                    fill=(int(40 * v * prof), int(220 * v * prof), int(255 * v * prof), 230))
    img.save(f"{RUTA_PREVIEW}/{nombre}.png")


def hornear(p, w, b, aristas, bisagra):
    b64 = lambda a: base64.b64encode(a.tobytes()).decode()
    txt = (
        "// Generado por esculpir_cara.py a partir de la malla facial canonica de\n"
        "// MediaPipe (Apache-2.0). No editar a mano.\n"
        "window.CARA_DATOS = {\n"
        f"  n: {len(p)},\n"
        f"  p: \"{b64(p.astype(np.float32))}\",\n"
        f"  w: \"{b64((w * 255).astype(np.uint8))}\",\n"
        f"  b: \"{b64((np.clip(b, 0, 1.4) / 1.4 * 255).astype(np.uint8))}\",\n"
        f"  e: \"{b64(aristas.astype(np.uint16))}\",\n"
        "  bisagra: [%.3f, %.3f],\n" % (bisagra[0], bisagra[1]) +
        "};\n"
    )
    open(RUTA_SALIDA, "w", encoding="utf-8").write(txt)
    print(f"horneado: {len(p)} puntos, {len(aristas)} aristas -> {RUTA_SALIDA} ({len(txt)//1024} KB)")


if __name__ == "__main__":
    V, F = cargar_obj(RUTA_OBJ)
    print(f"malla canonica: {len(V)} vertices, {len(F)} triangulos")

    e_malla = aristas_de_caras(F)
    print(f"aristas reales de la malla: {len(e_malla)}")

    # rasgos para el realce de brillo (labios, ojos, nariz, cejas)
    idx_rasgos = np.array([
        13, 14, 61, 291, 0, 17, 78, 308, 82, 312, 87, 317,           # labios
        33, 133, 159, 145, 362, 263, 386, 374, 157, 384,             # ojos
        1, 2, 4, 5, 6, 168, 197, 195, 94, 331, 102,                  # nariz
        70, 63, 105, 66, 107, 336, 296, 334, 293, 300,               # cejas
    ])

    # --- nube: nodos de la malla + relleno de la cara + craneo + orejas + cuello + ojos ---
    n_relleno, n_craneo, n_orejas, n_cuello, n_ojos = 3800, 2000, 260, 700, 320
    p_relleno = muestrear_triangulos(V, F, n_relleno)
    p_craneo = craneo(V, n_craneo)
    p_orejas = orejas(n_orejas)
    p_cuello = cuello(n_cuello)
    p_ojos = ojos(n_ojos)

    p = np.concatenate([V, p_relleno, p_craneo, p_orejas, p_cuello, p_ojos])
    n_nodos = len(V)
    es_nodo = np.zeros(len(p), bool); es_nodo[:n_nodos] = True
    ini_cuello = n_nodos + n_relleno + n_craneo + n_orejas
    es_cuello = np.zeros(len(p), bool); es_cuello[ini_cuello:ini_cuello + n_cuello] = True
    es_ojo = np.zeros(len(p), bool); es_ojo[ini_cuello + n_cuello:] = True

    # ⚠️ Pesos y brillo se calculan ANTES de centrar: sus referencias (la línea de
    # la boca, los rasgos) viven en las coordenadas de la malla canónica.
    w = peso_mandibula(p, es_cuello)
    b = brillo(p, V, idx_rasgos, es_nodo, es_ojo, es_cuello)

    # centrar la cabeza en el origen para que el HUD la encuadre bien;
    # la bisagra de la mandíbula viaja con ella
    desp = np.array([0.0, (p[:, 1].max() + p[:, 1].min()) / 2, p[:, 2].mean()])
    p -= desp
    bisagra = (BISAGRA_Y - desp[1], BISAGRA_Z - desp[2])

    # --- aristas: las reales de la cara + una red ligera para craneo y cuello ---
    resto = np.where(~es_nodo & ~es_ojo)[0]
    arbol = cKDTree(p[resto])
    dist, vec = arbol.query(p[resto], k=3)
    extra = set()
    for i in range(len(resto)):
        for j in (1, 2):
            if dist[i, j] < 1.25:
                a, c = sorted((int(resto[i]), int(resto[vec[i, j]])))
                extra.add((a, c))
    extra = np.array(sorted(extra), dtype=np.int32)
    if len(extra) > 6500:
        extra = extra[rng.choice(len(extra), 6500, replace=False)]
    aristas = np.concatenate([e_malla, extra])
    print(f"aristas totales: {len(aristas)} (malla {len(e_malla)} + red {len(extra)})")

    preview(p, b, aristas, "cara_frente", 0.0, bisagra=bisagra)
    preview(p, b, aristas, "cara_tres_cuartos", 0.42, bisagra=bisagra)
    preview(p, b, aristas, "cara_hablando", 0.42, ap=1.0, w=w, bisagra=bisagra)
    print(f"vistas previas listas (peso de mandibula: {w.max():.2f} max, "
          f"{(w > 0.5).sum()} puntos moviles)")

    if "--preview" not in sys.argv:
        hornear(p, w, b, aristas, bisagra)
