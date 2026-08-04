"""
¿Cuál de los dos rigs de retargeting mueve realmente al esqueleto?

'Armature' copia rotación de AnatPoseToTPose Y de TPoseToAnatPose (8 huesos de
cada uno), así que el nombre no alcanza para decidir. Se prueba: se asigna la
acción a un candidato, se avanza a un cuadro intermedio y se mide cuánto se
desplazaron las mallas anatómicas respecto del reposo. El que produce
movimiento real es el que maneja.
"""

import os

import bpy
from mathutils import Vector

# Sin esto Blender headless bloquea drivers y scripts del archivo, y la
# cadena de retargeting del rig no se evalúa: todo queda en reposo.
bpy.context.preferences.filepaths.use_scripts_auto_execute = True

BLEND = os.environ["BIOMECH_BLEND"]
ACTION = "Walk 1"

CANDIDATOS = ["AnatPoseToTPose", "TPoseToAnatPose", "Armature"]


def centroides(objs, dg):
    out = {}
    for o in objs:
        ev = o.evaluated_get(dg)
        m = ev.matrix_world
        c = Vector((0, 0, 0))
        for v in o.bound_box:
            c += m @ Vector(v)
        out[o.name] = c / 8
    return out


for cand in CANDIDATOS:
    bpy.ops.wm.open_mainfile(filepath=BLEND, use_scripts=True)
    arm = bpy.data.objects.get(cand)
    act = bpy.data.actions.get(ACTION)
    if not arm or not act:
        print(f"{cand:<20} falta armadura o acción")
        continue

    meshes = [o for o in bpy.data.objects
              if o.type == "MESH" and o.parent and o.parent_type == "BONE"
              and len(o.data.polygons)]

    scn = bpy.context.scene
    scn.frame_set(int(act.frame_range[0]))
    dg = bpy.context.evaluated_depsgraph_get()
    reposo = centroides(meshes, dg)

    if not arm.animation_data:
        arm.animation_data_create()
    arm.animation_data.action = act

    medio = int((act.frame_range[0] + act.frame_range[1]) / 2)
    scn.frame_set(medio)
    dg = bpy.context.evaluated_depsgraph_get()
    movido = centroides(meshes, dg)

    desplaz = [(movido[k] - reposo[k]).length for k in reposo]
    desplaz.sort(reverse=True)
    n_movidas = sum(1 for d in desplaz if d > 0.005)  # > 5 mm

    print(f"{cand:<20} mallas movidas >5mm: {n_movidas:>4}/{len(meshes)}   "
          f"máx {desplaz[0]*1000:7.1f} mm   mediana "
          f"{desplaz[len(desplaz)//2]*1000:6.1f} mm")
