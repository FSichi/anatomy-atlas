"""
¿Como se mueven los huesos si ninguna malla tiene modificador Armature?

Hipotesis: estan emparentadas a un hueso de la armadura (parent_type='BONE').
Es lo correcto para un esqueleto — un hueso es rigido, no se deforma — y
significa que la animacion es exportable a glTF sin rigear nada a mano.
"""

import os
from collections import Counter

import bpy

bpy.ops.wm.open_mainfile(filepath=os.environ["BIOMECH_BLEND"])

meshes = [o for o in bpy.data.objects if o.type == "MESH"]

print("=== Como estan emparentadas las mallas ===")
tipos = Counter(f"{o.parent_type if o.parent else 'sin padre'}"
                f"{' -> ' + o.parent.type if o.parent else ''}" for o in meshes)
for t, n in tipos.most_common():
    print(f"  {t:<28} {n:>5}")

boned = [o for o in meshes if o.parent and o.parent_type == "BONE"]
print(f"\nMallas emparentadas a un hueso: {len(boned)} de {len(meshes)}")
for o in boned[:12]:
    print(f"    {o.name[:44]:<46} hueso='{o.parent_bone}'")

# ¿Que armadura las mueve?
arms = Counter(o.parent.name for o in boned if o.parent)
print("\n  armadura que las controla:")
for a, n in arms.most_common():
    print(f"    {a:<32} {n} mallas")

# Cobertura: cuantos huesos de la armadura anatomica tienen malla colgando
main = bpy.data.objects.get("Armature")
if main:
    usados = {o.parent_bone for o in boned if o.parent and o.parent.name == "Armature"}
    print(f"\n  huesos de 'Armature' con malla: {len(usados)} de {len(main.data.bones)}")
    faltan = [b.name for b in main.data.bones if b.name not in usados]
    print(f"  huesos sin malla (muestra): {faltan[:10]}")

# Constraints: la cadena de retargeting
print("\n=== Restricciones en las armaduras (cadena de retargeting) ===")
for a in [o for o in bpy.data.objects if o.type == "ARMATURE"]:
    con = Counter(c.type for pb in a.pose.bones for c in pb.constraints)
    print(f"  {a.name:<24} {dict(con) if con else 'sin restricciones'}")

print("\n=== Escala de la escena ===")
lo = [1e9] * 3
hi = [-1e9] * 3
for o in meshes[:400]:
    for c in o.bound_box:
        w = o.matrix_world @ __import__("mathutils").Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], w[i])
            hi[i] = max(hi[i], w[i])
print(f"  Z {lo[2]:.3f} .. {hi[2]:.3f}   alto {hi[2]-lo[2]:.3f}")
