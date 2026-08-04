"""
Tres preguntas que deciden si Z-Anatomy sirve como fuente:

  1. En que escala esta la escena.
  2. Que son las mallas con sufijo .j (sospecha: agregados que duplican
     geometria de sus hijos; si es asi, exportarlas duplicaria el peso).
  3. Cuantas de las 306 "peripheral nervous system" son nervios de verdad y
     cuantas son musculos inervados listados ahi con fines didacticos.
"""

import os
import re
from collections import defaultdict

import bpy
from mathutils import Vector

bpy.ops.wm.open_mainfile(filepath=os.environ["ZANATOMY_BLEND"])

meshes = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.vertices)]

# ── 1. Escala ───────────────────────────────────────────────────────
lo = Vector((1e9,) * 3)
hi = Vector((-1e9,) * 3)
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], w[i])
            hi[i] = max(hi[i], w[i])
size = hi - lo
print("=== Escala ===")
for i, ax in enumerate("XYZ"):
    print(f"  {ax}  {lo[i]:9.2f} .. {hi[i]:9.2f}   extension {size[i]:8.2f}")
up = max(range(3), key=lambda i: size[i])
print(f"  eje vertical probable: {'XYZ'[up]}  altura {size[up]:.2f} unidades")
print(f"  -> factor a milimetros: x{1700 / size[up]:.1f} (asumiendo 1,70 m)")

# ── 2. Que son los .j ───────────────────────────────────────────────
print("\n=== Mallas con sufijo .j ===")
j = [o for o in meshes if o.name.endswith(".j")]
print(f"  cantidad: {len(j)}")
tot_j = sum(len(o.data.polygons) for o in j)
tot_all = sum(len(o.data.polygons) for o in meshes)
print(f"  poligonos en .j : {tot_j:,}  ({100 * tot_j / tot_all:.0f}% del total)")
print("  ejemplos (nombre / poligonos / hijos en la escena):")
for o in j[:8]:
    print(f"    {o.name[:44]:<46} {len(o.data.polygons):>7,}  hijos={len(o.children)}")

# ¿El .j duplica a sus hijos? Comparar poligonos con los de su coleccion.
print("\n  comprobacion de duplicacion:")
for o in j[:6]:
    cols = [c for c in bpy.data.collections if o.name in c.objects]
    if not cols:
        continue
    col = cols[0]
    hermanos = [x for x in col.all_objects
                if x.type == "MESH" and x is not o and len(x.data.vertices)]
    sib_polys = sum(len(x.data.polygons) for x in hermanos)
    print(f"    {o.name[:36]:<38} propio={len(o.data.polygons):>7,}  "
          f"hermanos={sib_polys:>8,}  ({len(hermanos)} objs)")

# ── 3. Pureza de la coleccion de nervios perifericos ───────────────
print("\n=== Que hay realmente en 'Peripheral nervous system' ===")
col = next((c for c in bpy.data.collections if c.name == "Peripheral nervous system"), None)
objs = [o for o in col.all_objects if o.type == "MESH" and len(o.data.vertices)]

NERVE_WORDS = ("nerve", "nervous", "plexus", "gangli", "trunk", "ramus", "rami",
               "root", "cord", "chorda", "sympathetic", "parasympathetic")
MUSCLE_WORDS = ("muscle", "tendon", "tarsus", "aponeurosis", "raphe", "ring")

kind = defaultdict(list)
for o in objs:
    n = o.name.lower()
    if any(w in n for w in MUSCLE_WORDS):
        kind["musculo/otro"].append(o.name)
    elif any(w in n for w in NERVE_WORDS):
        kind["nervio"].append(o.name)
    else:
        kind["indeterminado"].append(o.name)

for k in ("nervio", "musculo/otro", "indeterminado"):
    print(f"  {k:<16} {len(kind[k]):>4}")
    for s in kind[k][:6]:
        print(f"        {s[:64]}")

# Sin los .j (que son agregados)
solo = [o for o in objs if not o.name.endswith(".j")]
print(f"\n  sin agregados .j : {len(solo)} de {len(objs)}")
