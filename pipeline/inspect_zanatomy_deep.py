"""
Detalle de los sistemas nervioso y cardiovascular de Z-Anatomy.

La busqueda por palabra clave puede enganarse con la nomenclatura, asi que acá
se listan las subcolecciones reales y una muestra de nombres.
"""

import os

import bpy

bpy.ops.wm.open_mainfile(filepath=os.environ["ZANATOMY_BLEND"])


def walk(col, depth=0, limit_depth=3):
    n = len([o for o in col.all_objects if o.type == "MESH"])
    direct = len([o for o in col.objects if o.type == "MESH"])
    print(f"{'  ' * depth}{col.name[:52]:<54} {n:>5} ({direct} propias)")
    if depth < limit_depth:
        for sub in col.children:
            walk(sub, depth + 1, limit_depth)


root = bpy.context.scene.collection
for target in ("5: Cardiovascular system", "7: Nervous system & Sense organs"):
    col = next((c for c in root.children if c.name == target), None)
    if not col:
        print(f"\n!! no encontrada: {target}")
        continue
    print(f"\n=== {target} ===")
    walk(col)
    print("  --- muestra de nombres ---")
    for o in [o for o in col.all_objects if o.type == "MESH"][:28]:
        print(f"      {o.name[:66]}")

# Tambien la del bonus, que es donde suele estar el detalle fino
bonus = next((c for c in root.children if c.name.startswith("Bonus")), None)
if bonus:
    for target in ("Cardiovascular system", "Nervous system"):
        col = next((c for c in bonus.children if c.name == target), None)
        if not col:
            continue
        print(f"\n=== Bonus / {target} ===")
        walk(col, limit_depth=2)
        for o in [o for o in col.all_objects if o.type == "MESH"][:16]:
            print(f"      {o.name[:66]}")
