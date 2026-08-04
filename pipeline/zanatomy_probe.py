"""
Sondeo de Z-Anatomy: escala, orientacion y convencion de nombres.

Antes de escribir el exportador hay que saber tres cosas:
  1. en que unidades esta (BodyParts3D esta en milimetros)
  2. que eje es "arriba"
  3. si los nombres permiten mapear a Terminologia Anatomica

Sin esto, cualquier pipeline sale torcido.
"""

import os
import re
from collections import Counter, defaultdict

import bpy
from mathutils import Vector

bpy.ops.wm.open_mainfile(filepath=os.environ["ZANATOMY_BLEND"])

meshes = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.vertices)]
print(f"Mallas con geometria: {len(meshes)}\n")

# ── 1. Caja global y escala ────────────────────────────────────────
lo = Vector((1e9, 1e9, 1e9))
hi = Vector((-1e9, -1e9, -1e9))
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        lo = Vector((min(lo[i], w[i]) for i in range(3)))
        hi = Vector((max(hi[i], w[i]) for i in range(3)))

size = hi - lo
print("=== Caja global (unidades de Blender) ===")
for i, ax in enumerate("XYZ"):
    print(f"  {ax}  {lo[i]:9.2f} .. {hi[i]:9.2f}   extension {size[i]:8.2f}")

up = max(range(3), key=lambda i: size[i])
print(f"\n  eje mas largo (probable altura): {'XYZ'[up]} = {size[up]:.2f}")
print(f"  unidad de escena: {bpy.context.scene.unit_settings.scale_length}")
print(f"  sistema         : {bpy.context.scene.unit_settings.system}")

# Un humano mide ~1,7 m. Deducimos el factor a milimetros.
h = size[up]
for label, factor in (("metros", 1000.0), ("decimetros", 100.0),
                      ("centimetros", 10.0), ("milimetros", 1.0)):
    if 1.4 <= h * factor / 1000 <= 2.1:
        print(f"  => la escena parece estar en {label}: x{factor:g} para pasar a mm")

# ── 2. Convencion de nombres ───────────────────────────────────────
print("\n=== Sufijos de nombre ===")
suf = Counter()
for o in meshes:
    m = re.search(r"\.([a-z]+)(\.\d+)?$", o.name)
    suf[m.group(1) if m else "(sin sufijo)"] += 1
for s, n in suf.most_common(12):
    print(f"  .{s:<12} {n:>5}")

print("\n=== Muestra de nombres por sistema ===")
root = bpy.context.scene.collection


def sample(colname, n=10):
    col = next((c for c in bpy.data.collections if c.name == colname), None)
    if not col:
        print(f"  !! sin coleccion {colname}")
        return
    objs = [o for o in col.all_objects if o.type == "MESH"]
    print(f"\n  [{colname}]  {len(objs)} mallas")
    for o in objs[:n]:
        print(f"     {o.name[:70]}")


for c in ("Peripheral nervous system", "Cranial nerves", "Spinal nerves",
          "Cardiovascular system", "Joints"):
    sample(c)

# ── 3. Datos personalizados: quiza traigan IDs ─────────────────────
print("\n=== Propiedades personalizadas (primeras mallas que tengan) ===")
shown = 0
for o in meshes:
    keys = [k for k in o.keys() if not k.startswith("_")]
    if keys and shown < 6:
        print(f"  {o.name[:44]:<46} {  {k: o[k] for k in keys}  }")
        shown += 1
if not shown:
    print("  ninguna: los nombres son el unico identificador")
