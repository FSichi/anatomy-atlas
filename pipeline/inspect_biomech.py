"""
¿Z-Biomechanics trae animación usable?

Lo que decide si se puede mostrar movimiento articular sin rigear a mano:
  - armaduras (esqueletos de deformación) y cuántos huesos tienen
  - acciones / animation data (movimientos ya autorados)
  - shape keys (deformaciones fisiológicas: latido, respiración)
  - modificadores Armature en las mallas (o sea, skinning real)
"""

import os
from collections import defaultdict

import bpy

bpy.ops.wm.open_mainfile(filepath=os.environ["BIOMECH_BLEND"])

objs = list(bpy.data.objects)
por_tipo = defaultdict(int)
for o in objs:
    por_tipo[o.type] += 1

print("=== Objetos por tipo ===")
for t, n in sorted(por_tipo.items(), key=lambda x: -x[1]):
    print(f"  {t:<12} {n:>5}")

print("\n=== Armaduras ===")
arms = [o for o in objs if o.type == "ARMATURE"]
print(f"  cantidad: {len(arms)}")
for a in arms[:10]:
    print(f"    {a.name[:44]:<46} {len(a.data.bones)} huesos")
    for b in list(a.data.bones)[:8]:
        print(f"        {b.name[:52]}")

print("\n=== Acciones (movimientos autorados) ===")
acts = list(bpy.data.actions)
print(f"  cantidad: {len(acts)}")


def curve_count(a):
    """Blender 5 movio las fcurves a slots/layers; se prueban ambas formas."""
    n = len(getattr(a, "fcurves", []) or [])
    if n:
        return n
    for layer in getattr(a, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            for bag in getattr(strip, "channelbags", []) or []:
                n += len(getattr(bag, "fcurves", []) or [])
    return n


for a in acts:
    fr = a.frame_range
    print(f"    {a.name[:46]:<48} cuadros {fr[0]:.0f}..{fr[1]:.0f}  "
          f"curvas={curve_count(a)}")

print("\n=== Mallas con modificador Armature (skinning) ===")
skinned = [o for o in objs if o.type == "MESH"
           and any(m.type == "ARMATURE" for m in o.modifiers)]
print(f"  cantidad: {len(skinned)}")
for o in skinned[:10]:
    print(f"    {o.name[:52]}")

print("\n=== Shape keys (deformación fisiológica) ===")
sk = [o for o in objs if o.type == "MESH" and o.data.shape_keys]
print(f"  mallas con shape keys: {len(sk)}")
for o in sk[:10]:
    keys = [k.name for k in o.data.shape_keys.key_blocks]
    print(f"    {o.name[:38]:<40} {keys[:5]}")

print("\n=== Objetos con animación propia ===")
anim = [o for o in objs if o.animation_data and o.animation_data.action]
print(f"  cantidad: {len(anim)}")
for o in anim[:12]:
    print(f"    {o.name[:40]:<42} accion={o.animation_data.action.name[:28]}")

print("\n=== Colecciones de primer nivel ===")
for c in bpy.context.scene.collection.children:
    n = len([o for o in c.all_objects if o.type == "MESH"])
    print(f"  {c.name[:52]:<54} {n:>5} mallas")
