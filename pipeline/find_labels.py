"""
Identifica las mallas que flotan al costado del cuerpo.

En las capturas se ven fragmentos claros formando letras a la izquierda del
modelo. La caja global de Z-Anatomy ya lo insinuaba: X va de -1,003 a 0,342,
o sea asimetrica, cuando un cuerpo deberia ser simetrico en ese eje.
"""

import os
from collections import defaultdict

import bpy
from mathutils import Vector

bpy.ops.wm.open_mainfile(filepath=os.environ["ZANATOMY_BLEND"])

meshes = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons)]


def world_box(o):
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], w[i])
            hi[i] = max(hi[i], w[i])
    return lo, hi


boxes = {o.name: world_box(o) for o in meshes}

# El cuerpo real deberia ser simetrico en X. Buscamos lo que se va muy a la
# izquierda: el ancho de hombros no pasa de ~0,25 a cada lado.
fuera = [(n, b) for n, b in boxes.items() if b[0][0] < -0.45]
print(f"Mallas con X < -0,45 (fuera del cuerpo): {len(fuera)}\n")

for n, (lo, hi) in sorted(fuera, key=lambda x: x[1][0][0])[:20]:
    print(f"  X {lo[0]:7.2f}..{hi[0]:6.2f}  Z {lo[2]:6.2f}  {n[:52]}")

# ¿En que colecciones estan?
print("\n=== Colecciones que las contienen ===")
por_col = defaultdict(int)
nombres_fuera = {n for n, _ in fuera}
for col in bpy.data.collections:
    hit = sum(1 for o in col.objects if o.name in nombres_fuera)
    if hit:
        por_col[col.name] += hit
for c, n in sorted(por_col.items(), key=lambda x: -x[1])[:15]:
    print(f"  {n:>5}  {c[:60]}")

# ¿Tienen algo en comun sus datos? (las etiquetas suelen venir de texto)
print("\n=== Origen de los datos de malla ===")
tipos = defaultdict(int)
for n, _ in fuera:
    o = bpy.data.objects[n]
    tipos[o.data.name.split(".")[0][:30]] += 1
for t, c in sorted(tipos.items(), key=lambda x: -x[1])[:12]:
    print(f"  {c:>5}  data='{t}'")

# Contraste: cuantas mallas quedan si filtramos por X
dentro = len(meshes) - len(fuera)
print(f"\nMallas dentro del cuerpo: {dentro} de {len(meshes)}")
