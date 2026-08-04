"""
Diagnóstico al nivel del hueso: ¿la acción mueve algo, y hasta dónde llega?

Se mide en tres escalones para ver dónde se corta la cadena:
  1. los huesos de la armadura a la que se asigna la acción
  2. los huesos de 'Armature' (el rig anatómico)
  3. las mallas emparentadas a esos huesos
"""

import os

import bpy
from mathutils import Vector

bpy.context.preferences.filepaths.use_scripts_auto_execute = True

BLEND = os.environ["BIOMECH_BLEND"]
ACTION = os.environ.get("ACTION", "Walk 1")



def bind(obj, act):
    """Asigna la acción y ENLAZA EL SLOT.

    Desde Blender 4.4 las acciones tienen slots: sin enlazar uno, la acción
    queda asignada pero ningún canal se aplica. Era la causa de que el horneado
    capturara la pose de reposo y el movimiento saliera basura.
    """
    ad = obj.animation_data or obj.animation_data_create()
    ad.action = act
    if hasattr(ad, "action_slot"):
        cands = list(getattr(ad, "action_suitable_slots", [])) or list(getattr(act, "slots", []))
        if cands:
            ad.action_slot = cands[0]
    return ad

def pose_snapshot(arm):
    return {pb.name: pb.matrix.translation.copy() for pb in arm.pose.bones}


def moved(a, b, umbral=0.005):
    return sum(1 for k in a if (b[k] - a[k]).length > umbral)


for cand in ["AnatPoseToTPose", "TPoseToAnatPose"]:
    bpy.ops.wm.open_mainfile(filepath=BLEND, use_scripts=True)
    scn = bpy.context.scene
    arm = bpy.data.objects[cand]
    main = bpy.data.objects["Armature"]
    act = bpy.data.actions[ACTION]

    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    scn.frame_set(f0)
    bpy.context.view_layer.update()
    a_cand, a_main = pose_snapshot(arm), pose_snapshot(main)

    bind(arm, act)
    bpy.context.view_layer.update()

    scn.frame_set((f0 + f1) // 2)
    bpy.context.view_layer.update()
    b_cand, b_main = pose_snapshot(arm), pose_snapshot(main)

    print(f"\n=== acción '{ACTION}' sobre {cand} ===")
    print(f"  huesos movidos en {cand:<18} {moved(a_cand, b_cand):>4}/{len(a_cand)}")
    print(f"  huesos movidos en Armature          {moved(a_main, b_main):>4}/{len(a_main)}")
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent
              and o.parent_type == "BONE" and len(o.data.polygons)]
    dg = bpy.context.evaluated_depsgraph_get()
    pos = {o.name: o.evaluated_get(dg).matrix_world.translation.copy() for o in meshes}
    scn.frame_set(f0)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    pos0 = {o.name: o.evaluated_get(dg).matrix_world.translation.copy() for o in meshes}
    nm = sum(1 for k in pos0 if (pos[k] - pos0[k]).length > 0.005)
    print(f"  MALLAS movidas                      {nm:>4}/{len(meshes)}")

    d = sorted(((b_cand[k] - a_cand[k]).length, k) for k in a_cand)
    print(f"  mayor desplazamiento en {cand}: "
          f"{d[-1][0]*1000:.0f} mm en '{d[-1][1]}'")

# ¿Y si la acción va directamente sobre 'Armature' pero con los nombres que sí
# existen? Se prueba una acción propia del rig anatómico, para confirmar que la
# maquinaria de reproducción funciona.
bpy.ops.wm.open_mainfile(filepath=BLEND, use_scripts=True)
scn = bpy.context.scene
main = bpy.data.objects["Armature"]
for nombre in ("Walk", "Yoga-flex", "Foetal pose"):
    act = bpy.data.actions.get(nombre)
    if not act:
        continue
    scn.frame_set(0)
    bpy.context.view_layer.update()
    a = pose_snapshot(main)
    bind(main, act)
    bpy.context.view_layer.update()
    b = pose_snapshot(main)
    print(f"\n=== '{nombre}' directo sobre Armature (pose, 1 cuadro) ===")
    print(f"  huesos movidos: {moved(a, b)}/{len(a)}")
    d = sorted(((b[k] - a[k]).length, k) for k in a)
    print(f"  mayor: {d[-1][0]*1000:.0f} mm en '{d[-1][1]}'")
