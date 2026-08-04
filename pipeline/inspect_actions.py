"""
¿A qué armadura pertenece cada acción?

Sospecha: las acciones de 96 curvas (32 huesos x 3 canales) son del rig de
captura de movimiento de 31 huesos, no del rig anatómico de 237. Si se le
asignan al anatómico, Blender empareja las curvas POR NOMBRE de hueso — y como
casi ningún nombre coincide, el resultado es ruido.

Se listan los huesos que cada acción realmente controla y contra qué armadura
encajan.
"""

import os
import re
from collections import Counter

import bpy

bpy.ops.wm.open_mainfile(filepath=os.environ["BIOMECH_BLEND"])

arms = {a.name: {b.name for b in a.data.bones}
        for a in bpy.data.objects if a.type == "ARMATURE"}
print("=== Armaduras ===")
for n, bones in arms.items():
    print(f"  {n:<20} {len(bones):>4} huesos")


def curves(a):
    out = list(getattr(a, "fcurves", []) or [])
    if out:
        return out
    for layer in getattr(a, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            for bag in getattr(strip, "channelbags", []) or []:
                out.extend(getattr(bag, "fcurves", []) or [])
    return out


BONE_RE = re.compile(r'pose\.bones\["([^"]+)"\]')

print("\n=== A qué armadura pertenece cada acción ===")
print(f"{'acción':<34}{'curvas':>7}{'huesos':>8}   encaje por armadura")
print("-" * 92)

for act in sorted(bpy.data.actions, key=lambda a: a.name):
    fcs = curves(act)
    bones = {m.group(1) for fc in fcs
             if (m := BONE_RE.search(fc.data_path or ""))}
    if not bones:
        print(f"{act.name[:32]:<34}{len(fcs):>7}{0:>8}   (no anima huesos)")
        continue
    encaje = {
        n: f"{len(bones & bset)}/{len(bones)}"
        for n, bset in arms.items()
    }
    mejor = max(arms, key=lambda n: len(bones & arms[n]))
    print(f"{act.name[:32]:<34}{len(fcs):>7}{len(bones):>8}   "
          f"{encaje}  -> {mejor}")

print("\n=== Muestra de huesos que anima 'Walk 1' ===")
w = bpy.data.actions.get("Walk 1")
if w:
    bones = sorted({m.group(1) for fc in curves(w)
                    if (m := BONE_RE.search(fc.data_path or ""))})
    print(f"  {bones[:14]}")

print("\n=== Restricciones de 'Armature' que copian de otra armadura ===")
main = bpy.data.objects.get("Armature")
if main:
    fuentes = Counter()
    for pb in main.pose.bones:
        for c in pb.constraints:
            tgt = getattr(c, "target", None)
            if tgt:
                fuentes[f"{c.type} <- {tgt.name}"] += 1
    for k, v in fuentes.most_common(10):
        print(f"  {v:>4}  {k}")
