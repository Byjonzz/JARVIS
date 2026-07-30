# -*- coding: utf-8 -*-
"""Escultor de la cabeza holografica de I.R.I.S.

Construye una CABEZA COMPLETA mallada a partir de la malla facial canonica de
MediaPipe (assets/canonical_face_model.obj, Apache-2.0): 468 vertices y 898
triangulos de una cara humana promedio real. No son datos biometricos de nadie:
es la geometria facial media que la industria usa para colocar filtros.

Que anade sobre la malla canonica (que solo cubre el rostro):
  - Craneo: anillos que nacen del borde de la cara y barren hasta la nuca,
    TRIANGULADOS, de modo que el alambrado es continuo por toda la cabeza.
  - Cuello y orejas, tambien mallados.
  - Subdivision de Loop: cuadruplica los triangulos y suaviza la superficie,
    que es lo que da el aspecto denso de las referencias.
  - Brillo de contorno (rim): los puntos cuya normal mira de canto respecto a la
    camara se encienden; es lo que hace que la silueta resplandezca.

Salidas:
  assets/cara_datos.js  — nube de puntos, pesos de mandibula, brillos y aristas
  cara_*.png            — vistas previas para iterar la forma

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

BISAGRA_Y, BISAGRA_Z = 0.67, -2.44     # articulacion temporomandibular (junto a las orejas)
LINEA_BOCA_Y = -4.25                   # entre los labios internos (vertices 13 y 14)
VISTA = np.array([0.42, 0.10, 0.90])   # direccion de camara para el brillo de contorno


# ═══════════ malla: carga, topologia y subdivision ═══════════
def cargar_obj(ruta):
    V, F = [], []
    for linea in open(ruta, encoding="utf-8"):
        if linea.startswith("v "):
            V.append([float(x) for x in linea.split()[1:4]])
        elif linea.startswith("f "):
            F.append([int(t.split("/")[0]) - 1 for t in linea.split()[1:4]])
    return np.array(V, float), np.array(F, int)


def aristas(F):
    e = set()
    for a, b, c in F:
        for i, j in ((a, b), (b, c), (c, a)):
            e.add((min(i, j), max(i, j)))
    return np.array(sorted(e), dtype=np.int64)


def borde_ordenado(F):
    """Bucle de vertices del borde de la malla (el ovalo de la cara)."""
    cuenta = {}
    for a, b, c in F:
        for i, j in ((a, b), (b, c), (c, a)):
            k = (min(i, j), max(i, j))
            cuenta[k] = cuenta.get(k, 0) + 1
    bordes = [k for k, v in cuenta.items() if v == 1]
    vecinos = {}
    for a, b in bordes:
        vecinos.setdefault(a, []).append(b)
        vecinos.setdefault(b, []).append(a)
    inicio = bordes[0][0]
    bucle, actual, previo = [inicio], inicio, None
    while True:
        sig = [v for v in vecinos[actual] if v != previo]
        if not sig or sig[0] == inicio:
            break
        previo, actual = actual, sig[0]
        bucle.append(actual)
    return np.array(bucle)


def subdividir_loop(V, F):
    """Subdivision de Loop: 1 triangulo → 4, con suavizado. Cuadruplica la densidad."""
    borde_cuenta = {}
    caras_de_arista = {}
    for t, (a, b, c) in enumerate(F):
        for i, j in ((a, b), (b, c), (c, a)):
            k = (min(i, j), max(i, j))
            borde_cuenta[k] = borde_cuenta.get(k, 0) + 1
            caras_de_arista.setdefault(k, []).append(t)

    # vertices nuevos, uno por arista
    nuevo_idx, V_nuevos = {}, []
    for k, veces in borde_cuenta.items():
        a, b = k
        if veces == 1:                                   # arista de borde: punto medio
            p = 0.5 * (V[a] + V[b])
        else:                                            # interior: 3/8 + 1/8
            opuestos = []
            for t in caras_de_arista[k]:
                for v in F[t]:
                    if v != a and v != b:
                        opuestos.append(v)
            p = 0.375 * (V[a] + V[b]) + 0.125 * (V[opuestos[0]] + V[opuestos[1]])
        nuevo_idx[k] = len(V) + len(V_nuevos)
        V_nuevos.append(p)

    # reposicionar los vertices originales
    vecinos = {}
    for (a, b) in borde_cuenta:
        vecinos.setdefault(a, set()).add(b)
        vecinos.setdefault(b, set()).add(a)
    en_borde = set()
    for k, veces in borde_cuenta.items():
        if veces == 1:
            en_borde.update(k)
    V_viejos = V.copy()
    for i in range(len(V)):
        vs = list(vecinos.get(i, []))
        if not vs:
            continue
        if i in en_borde:
            vb = [j for j in vs if j in en_borde]
            if len(vb) == 2:
                V_viejos[i] = 0.75 * V[i] + 0.125 * (V[vb[0]] + V[vb[1]])
        else:
            n = len(vs)
            beta = (5.0 / 8.0 - (3.0 / 8.0 + 0.25 * np.cos(2 * np.pi / n)) ** 2) / n
            V_viejos[i] = (1 - n * beta) * V[i] + beta * V[vs].sum(0)

    V2 = np.vstack([V_viejos, np.array(V_nuevos)])
    F2 = []
    for a, b, c in F:
        ab = nuevo_idx[(min(a, b), max(a, b))]
        bc = nuevo_idx[(min(b, c), max(b, c))]
        ca = nuevo_idx[(min(c, a), max(c, a))]
        F2 += [[a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca]]
    return V2, np.array(F2, int)


def normales(V, F):
    n = np.zeros_like(V)
    A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    cara = np.cross(B - A, C - A)
    for k in range(3):
        np.add.at(n, F[:, k], cara)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)


# ═══════════ craneo, cuello y orejas: mallas de verdad ═══════════
def craneo_mallado(V, bucle, n_anillos=11):
    """Anillos que nacen del borde de la cara y barren hasta la nuca."""
    C = np.array([0.0, 1.6, 0.4])
    R = np.array([8.0, 9.2, 8.6])
    polo = np.array([0.0, 0.30, -1.0]); polo /= np.linalg.norm(polo)

    B = V[bucle]
    d = (B - C) / R
    d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)

    Vn, anillos = [], [bucle.tolist()]
    for k in range(1, n_anillos + 1):
        t = k / (n_anillos + 1)
        # slerp de cada direccion del borde hacia el polo trasero
        cos = np.clip(d @ polo, -1, 1)
        ang = np.arccos(cos)[:, None]
        s = np.sin(ang)
        dir_t = np.where(s > 1e-6,
                         (np.sin((1 - t) * ang) * d + np.sin(t * ang) * polo) / np.maximum(s, 1e-6),
                         d)
        dir_t /= np.maximum(np.linalg.norm(dir_t, axis=1, keepdims=True), 1e-9)
        p = C + R * dir_t
        mezcla = np.clip(t / 0.22, 0, 1)[None] if np.ndim(t) else min(t / 0.22, 1.0)
        p = B * (1 - mezcla) + p * mezcla        # sin costura junto a la cara
        anillos.append(list(range(len(V) + len(Vn), len(V) + len(Vn) + len(p))))
        Vn.append(p)
    polo_pos = C + R * polo
    idx_polo = len(V) + sum(len(a) for a in Vn)
    Vn.append(polo_pos[None])

    F = []
    for a, b in zip(anillos[:-1], anillos[1:]):
        m = len(a)
        for i in range(m):
            j = (i + 1) % m
            F += [[a[i], b[i], b[j]], [a[i], b[j], a[j]]]
    ult = anillos[-1]
    for i in range(len(ult)):
        F.append([ult[i], idx_polo, ult[(i + 1) % len(ult)]])
    return np.vstack(Vn), np.array(F, int)


def _anillos_a_malla(base, anillos_pos, cerrar_punta=False):
    """Convierte una lista de anillos de puntos en malla triangulada."""
    n_lados = len(anillos_pos[0])
    idx, off = [], base
    for _ in anillos_pos:
        idx.append(list(range(off, off + n_lados)))
        off += n_lados
    F = []
    for a, b in zip(idx[:-1], idx[1:]):
        for i in range(n_lados):
            j = (i + 1) % n_lados
            F += [[a[i], b[i], b[j]], [a[i], b[j], a[j]]]
    return np.vstack(anillos_pos), np.array(F, int)


def tubo_mallado(base, ejes, radios, n_lados=24, achata=1.0):
    """Malla tubular (cuello) siguiendo un eje con radios variables."""
    th = np.linspace(0, 2 * np.pi, n_lados, endpoint=False)
    anillos = [c + np.stack([r * np.cos(th), np.zeros(n_lados), r * achata * np.sin(th)], 1)
               for c, r in zip(ejes, radios)]
    return _anillos_a_malla(base, anillos)


def oreja_mallada(base, lado, n_u=16, n_v=7):
    """Pabellon auricular: cupula achatada pegada al lateral de la cabeza."""
    u = np.linspace(0, 2 * np.pi, n_u, endpoint=False)
    anillos = []
    for vv in np.linspace(0.06, 1.0, n_v):
        s = np.sin(vv * np.pi / 2)
        y = 0.9 + 2.30 * s * np.sin(u)
        z = -2.1 + 1.45 * s * np.cos(u)
        x = np.full(n_u, lado * (7.05 + 0.80 * np.cos(vv * np.pi / 2)))
        anillos.append(np.stack([x, y, z], 1))
    return _anillos_a_malla(base, anillos)


def muestrear_triangulos(V, F, n):
    A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    areas = 0.5 * np.linalg.norm(np.cross(B - A, C - A), axis=1)
    idx = rng.choice(len(F), n, p=areas / areas.sum())
    u = rng.random((n, 1)); v = rng.random((n, 1))
    fuera = (u + v) > 1
    u[fuera] = 1 - u[fuera]; v[fuera] = 1 - v[fuera]
    return A[idx] + u * (B[idx] - A[idx]) + v * (C[idx] - A[idx]), idx


# ═══════════ pesos de habla y brillo ═══════════
def peso_mandibula(p, es_cuello):
    y = p[:, 1]
    t = np.clip((LINEA_BOCA_Y - y) / 0.75, 0, 1)
    w = t * t * (3 - 2 * t)
    w[es_cuello] = 0.0
    return w


def brillo(p, N, V_rasgos, es_nodo, es_ojo, es_cuello):
    # ✨ contorno: normal de canto respecto a la camara → la silueta resplandece.
    # La base no puede ser muy baja: el rim apaga por igual lo frontal y lo trasero,
    # y con base 0.10 el craneo entero desaparecia.
    rim = 1.0 - np.abs(N @ (VISTA / np.linalg.norm(VISTA)))
    b = 0.30 + 0.70 * rim ** 2.2
    # realce de rasgos (labios, ojos, nariz, cejas)
    d, _ = cKDTree(V_rasgos).query(p)
    b += np.clip(0.55 - d * 0.75, 0, 0.45)
    b[es_nodo] += 0.20
    b[es_ojo] = 1.20
    b[es_cuello] *= 0.60
    b -= np.clip((-9.0 - p[:, 1]) * 0.09, 0, 0.20)
    return np.clip(b, 0.04, 1.4)


def ojos(n):
    p = []
    for lado in (-1, 1):
        c = np.array([lado * 3.15, 2.75, 2.55])
        th = rng.random(n // 2) * 2 * np.pi
        cph = rng.random(n // 2) * 2 - 1
        sph = np.sqrt(1 - cph ** 2)
        q = c + 1.28 * np.stack([sph * np.cos(th), cph, sph * np.sin(th)], 1)
        p.append(q[q[:, 2] > c[2] - 0.15])
    return np.concatenate(p)


# ═══════════ vista previa ═══════════
def preview(p, b, aristas_ij, nombre, yaw, ap=0.0, w=None, bisagra=(BISAGRA_Y, BISAGRA_Z)):
    if ap > 0 and w is not None:
        p = p.copy()
        by, bz = bisagra
        dy = p[:, 1] - by; dz = p[:, 2] - bz
        ang = w * ap * 0.42
        p[:, 1] = by + dy * np.cos(ang) - dz * np.sin(ang)
        p[:, 2] = bz + dy * np.sin(ang) + dz * np.cos(ang)
    cy, sy = np.cos(yaw), np.sin(yaw)
    R = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    q = p @ R.T
    ancho, alto, esc = 680, 820, 26.0
    xs = (q[:, 0] * esc + ancho / 2).astype(int)
    ys = (alto / 2 - q[:, 1] * esc - 20).astype(int)
    img = Image.new("RGB", (ancho, alto), (4, 10, 22))
    dib = ImageDraw.Draw(img, "RGBA")
    for a1, a2 in aristas_ij:
        prof = np.clip((q[a1, 2] + 11) / 22, 0.12, 1)
        v = np.clip((b[a1] + b[a2]) * 0.5, 0, 1.2)
        dib.line([(xs[a1], ys[a1]), (xs[a2], ys[a2])],
                 fill=(int(20 * prof), int(150 * prof * (0.4 + v)), int(200 * prof * (0.4 + v)),
                       int(60 + 90 * v)), width=1)
    for i in np.argsort(q[:, 2]):
        v = float(np.clip(b[i], 0, 1.3))
        prof = float(np.clip((q[i, 2] + 11) / 22, 0.22, 1))
        r = 0 if v < 0.55 else (1 if v < 0.95 else 2)
        dib.ellipse([xs[i] - r, ys[i] - r, xs[i] + r, ys[i] + r],
                    fill=(int(90 * v * prof), int(230 * v * prof), int(255 * v * prof), 235))
    img.save(f"{RUTA_PREVIEW}/{nombre}.png")


def hornear(p, w, b, aristas_ij, bisagra):
    b64 = lambda a: base64.b64encode(a.tobytes()).decode()
    txt = (
        "// Generado por esculpir_cara.py a partir de la malla facial canonica de\n"
        "// MediaPipe (Apache-2.0), extendida a cabeza completa. No editar a mano.\n"
        "window.CARA_DATOS = {\n"
        f"  n: {len(p)},\n"
        f"  p: \"{b64(p.astype(np.float32))}\",\n"
        f"  w: \"{b64((w * 255).astype(np.uint8))}\",\n"
        f"  b: \"{b64((np.clip(b, 0, 1.4) / 1.4 * 255).astype(np.uint8))}\",\n"
        f"  e: \"{b64(aristas_ij.astype(np.uint16))}\",\n"
        "  bisagra: [%.3f, %.3f],\n" % (bisagra[0], bisagra[1]) +
        "};\n"
    )
    open(RUTA_SALIDA, "w", encoding="utf-8").write(txt)
    print(f"horneado: {len(p)} puntos, {len(aristas_ij)} aristas -> {RUTA_SALIDA} ({len(txt)//1024} KB)")


if __name__ == "__main__":
    Vc, Fc = cargar_obj(RUTA_OBJ)
    print(f"malla canonica: {len(Vc)} vertices, {len(Fc)} triangulos")

    bucle = borde_ordenado(Fc)
    print(f"borde del rostro: {len(bucle)} vertices")

    # --- cabeza completa: cara + craneo + cuello + orejas, todo mallado ---
    V = Vc.copy(); F = Fc.copy()
    Vk, Fk = craneo_mallado(V, bucle)
    V = np.vstack([V, Vk]); F = np.vstack([F, Fk])

    ejes = [np.array([0, -6.6, 0.6]), np.array([0, -9.0, 0.2]),
            np.array([0, -11.5, -0.2]), np.array([0, -14.2, -0.6])]
    Vn, Fn = tubo_mallado(len(V), ejes, [3.30, 3.15, 3.20, 3.45], achata=1.05)
    V = np.vstack([V, Vn]); F = np.vstack([F, Fn])

    for lado in (-1, 1):
        Vo, Fo = oreja_mallada(len(V), lado)
        V = np.vstack([V, Vo]); F = np.vstack([F, Fo])

    n_cuello_ini = len(Vc) + len(Vk)
    n_cuello_fin = n_cuello_ini + len(Vn)
    print(f"cabeza completa: {len(V)} vertices, {len(F)} triangulos")

    # --- densidad: subdivision de Loop ---
    marca_cuello = np.zeros(len(V), bool); marca_cuello[n_cuello_ini:n_cuello_fin] = True
    V, F = subdividir_loop(V, F)
    marca_cuello = np.concatenate([marca_cuello, np.zeros(len(V) - len(marca_cuello), bool)])
    print(f"subdividida: {len(V)} vertices, {len(F)} triangulos")

    N = normales(V, F)
    e_malla = aristas(F)
    print(f"aristas de la malla: {len(e_malla)}")

    idx_rasgos = np.array([
        13, 14, 61, 291, 0, 17, 78, 308, 82, 312, 87, 317,
        33, 133, 159, 145, 362, 263, 386, 374, 157, 384,
        1, 2, 4, 5, 6, 168, 197, 195, 94, 331, 102,
        70, 63, 105, 66, 107, 336, 296, 334, 293, 300,
    ])
    V_rasgos = Vc[idx_rasgos]

    # --- nube: vertices de la malla + polvo sobre la superficie + ojos ---
    n_polvo, n_ojos = 5200, 320
    p_polvo, tri_polvo = muestrear_triangulos(V, F, n_polvo)
    N_polvo = N[F[tri_polvo, 0]]
    p_ojos = ojos(n_ojos)

    p = np.concatenate([V, p_polvo, p_ojos])
    Np = np.concatenate([N, N_polvo, np.tile(np.array([0, 0, 1.0]), (len(p_ojos), 1))])
    es_nodo = np.zeros(len(p), bool); es_nodo[:len(V)] = True
    es_ojo = np.zeros(len(p), bool); es_ojo[len(V) + n_polvo:] = True
    es_cuello = np.zeros(len(p), bool)
    es_cuello[:len(V)] = marca_cuello
    es_cuello[len(V):len(V) + n_polvo] = marca_cuello[F[tri_polvo, 0]]

    w = peso_mandibula(p, es_cuello)
    b = brillo(p, Np, V_rasgos, es_nodo, es_ojo, es_cuello)

    desp = np.array([0.0, (p[:, 1].max() + p[:, 1].min()) / 2, p[:, 2].mean()])
    p -= desp
    bisagra = (BISAGRA_Y - desp[1], BISAGRA_Z - desp[2])

    # las aristas de la malla ya indexan los primeros len(V) puntos
    aris = e_malla
    if len(p) > 65535:
        print(f"⚠️ {len(p)} puntos supera el limite de indices de 16 bits; recortando polvo")
    print(f"aristas finales: {len(aris)}")

    preview(p, b, aris, "cara_frente", 0.0, bisagra=bisagra)
    preview(p, b, aris, "cara_tres_cuartos", 0.42, bisagra=bisagra)
    preview(p, b, aris, "cara_hablando", 0.42, ap=1.0, w=w, bisagra=bisagra)
    print(f"vistas previas listas ({(w > 0.5).sum()} puntos moviles)")

    if "--preview" not in sys.argv:
        hornear(p, w, b, aris, bisagra)
