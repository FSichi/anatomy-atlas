"""
¿Se pueden superponer BodyParts3D y Z-Anatomy?

Son dos cuerpos distintos, no el mismo escaneo. Para poder mezclarlos en una
sola escena hay que ajustar una transformacion de similitud (escala uniforme +
traslacion) y saber CUANTO error queda. Ese error decide si "Mix" es honesto o
si va a mostrar articulaciones flotando al lado del hueso.

Metodo: se emparejan huesos por nombre, se ajusta escala+traslacion con los
centroides de todos los pares, y se reporta el residuo por hueso.
"""

import csv
import os
from collections import defaultdict

import bpy
import numpy as np
import trimesh
from mathutils import Vector

RAW = os.environ["BP3D_RAW"]
STL = os.path.join(RAW, "stl")
trimesh.util.log.setLevel("ERROR")

# Huesos grandes e inconfundibles, presentes en ambas fuentes.
PAIRS = [
    ("FMA13322", "clavícula der", "Clavicle.r"),
    ("FMA13323", "clavícula izq", "Clavicle.l"),
    ("FMA23130", "húmero der", "Humerus.r"),
    ("FMA23131", "húmero izq", "Humerus.l"),
    ("FMA16586", "coxal der", "Hip bone.r"),
    ("FMA16587", "coxal izq", "Hip bone.l"),
    ("FMA24474", "fémur der", "Femur.r"),
    ("FMA24475", "fémur izq", "Femur.l"),
    ("FMA46565", "cráneo", "Skull"),
    ("FMA52748", "mandíbula", "Mandible"),
]


def bp3d_box(fma):
    p = os.path.join(STL, fma + ".stl")
    if not os.path.exists(p):
        return None
    m = trimesh.load(p, process=False, force="mesh")
    return m.bounds[0], m.bounds[1]


print("Abriendo Z-Anatomy…", flush=True)
bpy.ops.wm.open_mainfile(filepath=os.environ["ZANATOMY_BLEND"])

zobj = {}
for o in bpy.data.objects:
    if o.type == "MESH" and len(o.data.polygons):
        zobj.setdefault(o.name, o)


def za_find(name):
    """Nombre exacto, o el candidato mas corto que lo contenga."""
    if name in zobj:
        return zobj[name]
    base = name.split(".")[0].lower()
    side = name.split(".")[1] if "." in name else None
    cands = [
        n for n in zobj
        if base in n.lower() and (side is None or n.lower().endswith("." + side))
    ]
    if not cands:
        cands = [n for n in zobj if base in n.lower()]
    if not cands:
        return None
    pick = min(cands, key=len)
    print(f"    (aprox) '{name}' -> '{pick}'")
    return zobj[pick]


def za_box(name):
    o = za_find(name)
    if not o:
        return None
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], w[i])
            hi[i] = max(hi[i], w[i])
    return np.array(lo), np.array(hi)


# ── Recolectar pares ────────────────────────────────────────────────
rows = []
for fma, label, zname in PAIRS:
    a = bp3d_box(fma)
    b = za_box(zname)
    if not a or not b:
        print(f"  falta par: {label} ({'BP3D' if not a else 'ZA'})")
        continue
    ca = (a[0] + a[1]) / 2
    cb = (b[0] + b[1]) / 2
    da = np.linalg.norm(a[1] - a[0])   # diagonal, como medida de tamano
    db = np.linalg.norm(b[1] - b[0])
    rows.append((label, ca, cb, da, db))

if len(rows) < 3:
    raise SystemExit("\nDemasiados pares faltantes: revisar los nombres de Z-Anatomy.")

print(f"\nPares emparejados: {len(rows)}")

# ── Escala: mediana del cociente de diagonales ──────────────────────
scales = [da / db for _, _, _, da, db in rows]
scale = float(np.median(scales))
print(f"\n=== Escala ===")
print(f"  factor Z-Anatomy -> BodyParts3D : {scale:.1f}")
print(f"  dispersion (min..max)           : {min(scales):.1f} .. {max(scales):.1f}")
print(f"  -> variacion de {100 * (max(scales) - min(scales)) / scale:.0f}% entre huesos")

# ── Traslacion: promedio de la diferencia de centroides ya escalados ─
A = np.array([ca for _, ca, _, _, _ in rows])
B = np.array([cb for _, _, cb, _, _ in rows]) * scale
t = (A - B).mean(axis=0)

print(f"\n=== Traslacion (mm) ===")
print(f"  {t[0]:8.1f}  {t[1]:8.1f}  {t[2]:8.1f}")

# ── Residuo por hueso ───────────────────────────────────────────────
print(f"\n=== Residuo despues de alinear ===")
print(f"{'hueso':<20}{'error mm':>10}{'tamano mm':>12}{'error %':>10}")
print("-" * 52)
errs = []
for (label, ca, cb, da, db) in rows:
    pred = cb * scale + t
    e = float(np.linalg.norm(ca - pred))
    errs.append(e)
    print(f"{label:<20}{e:>10.1f}{da:>12.0f}{100 * e / da:>9.0f}%")
print("-" * 52)
print(f"{'mediana':<20}{np.median(errs):>10.1f}")
print(f"{'maximo':<20}{max(errs):>10.1f}")
