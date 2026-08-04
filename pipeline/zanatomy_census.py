"""
Censo honesto de Z-Anatomy, para compararlo con BodyParts3D sin autoenganos.

Reglas del conteo:
  - se excluyen los objetos sin poligonos (los `.j` son marcadores de etiqueta)
  - cada malla se cuenta UNA vez, en el primer sistema que la contiene segun un
    orden de prioridad; las colecciones de Z-Anatomy se solapan a proposito (los
    nervios listan los musculos que inervan) y contar por coleccion infla todo
"""

import os
from collections import defaultdict

import bpy
from mathutils import Vector

bpy.ops.wm.open_mainfile(filepath=os.environ["ZANATOMY_BLEND"])

real = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) > 0]
empty = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) == 0]

print(f"Objetos MESH totales : {len([o for o in bpy.data.objects if o.type == 'MESH'])}")
print(f"  con poligonos      : {len(real)}")
print(f"  vacios (.j y otros): {len(empty)}")

# Prioridad: lo mas especifico primero, para que un musculo listado bajo
# "nervios" quede contado como musculo y no infle la capa nerviosa.
PRIORITY = [
    ("skeletal", "1: Skeletal system"),
    ("joints", "3: Joints"),
    ("insertions", "2: Muscular insertions"),
    ("muscular", "4: Muscular system"),
    ("vascular", "5: Cardiovascular system"),
    ("lymphoid", "6: Lymphoid organs"),
    ("organs", "8: Visceral systems"),
    ("nervous", "7: Nervous system & Sense organs"),
]

member = defaultdict(set)
for key, colname in PRIORITY:
    col = next((c for c in bpy.data.collections if c.name == colname), None)
    if col:
        member[key] = {
            o.name for o in col.all_objects
            if o.type == "MESH" and len(o.data.polygons) > 0
        }

assigned = {}
for key, _ in PRIORITY:
    for name in member[key]:
        assigned.setdefault(name, key)

counts = defaultdict(int)
polys = defaultdict(int)
by_name = {o.name: o for o in real}
for name, key in assigned.items():
    counts[key] += 1
    polys[key] += len(by_name[name].data.polygons)

print("\n=== Censo sin solapamiento (cada malla contada una vez) ===")
print(f"{'sistema':<14}{'mallas':>8}{'poligonos':>14}")
print("-" * 36)
for key, _ in PRIORITY:
    print(f"{key:<14}{counts[key]:>8}{polys[key]:>14,}")
print(f"{'sin sistema':<14}{len(real) - len(assigned):>8}")
print("-" * 36)
print(f"{'TOTAL':<14}{len(real):>8}{sum(polys.values()):>14,}")

print("\n=== Nervios: cuantos son nervios por nombre ===")
NERVE = ("nerve", "plexus", "gangli", "ramus", "rami", "chorda")
nerv = [n for n, k in assigned.items() if k == "nervous"]
nerv_named = [n for n in nerv if any(w in n.lower() for w in NERVE)]
print(f"  en el sistema nervioso : {len(nerv)}")
print(f"  con nombre de nervio   : {len(nerv_named)}")
for n in sorted(nerv_named)[:16]:
    print(f"      {n[:62]}")

print("\n=== Vasos por nombre ===")
VESSEL = ("artery", "arteries", "vein", "veins", "sinus", "aorta", "trunk")
vas = [n for n, k in assigned.items() if k == "vascular"]
vas_named = [n for n in vas if any(w in n.lower() for w in VESSEL)]
print(f"  en cardiovascular      : {len(vas)}")
print(f"  con nombre de vaso     : {len(vas_named)}")
for n in sorted(vas_named)[:14]:
    print(f"      {n[:62]}")

lo = Vector((1e9,) * 3)
hi = Vector((-1e9,) * 3)
for o in real:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], w[i])
            hi[i] = max(hi[i], w[i])
print("\n=== Escala (solo geometria real) ===")
for i, ax in enumerate("XYZ"):
    print(f"  {ax}  {lo[i]:8.3f} .. {hi[i]:8.3f}   extension {(hi - lo)[i]:7.3f}")
