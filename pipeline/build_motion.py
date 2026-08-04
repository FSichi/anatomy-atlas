"""
Z-Biomechanics -> GLB animados, interpolando entre poses anatómicas.

POR QUÉ ASÍ Y NO CON LOS CLIPS DE CAPTURA
-----------------------------------------
El archivo trae dos familias de acciones:

  - clips de captura (Walk 1, Jog, Jumps…): 96 curvas sobre un rig auxiliar de
    31 huesos con nomenclatura de mocap (Hips, LeftUpLeg, LeftFoot…)
  - poses anatómicas (Walk, Relax, Yoga-flex, Push up-up/down…): 5131 curvas
    sobre 'Armature', el rig de 237 huesos al que cuelgan las 271 mallas

Los clips de captura NO llegan al esqueleto. La cadena de retargeting pasa por
drivers que invocan funciones registradas por el addon de Z-Anatomy, y bpy
headless no lo carga: la consola escupe `NameError: name 'test' is not defined`
desde <bpy driver> y las restricciones quedan sin evaluar. Medido: animando el
rig de captura se mueven 11-13 de sus 31 huesos y 0 de los 237 anatómicos.

Las poses anatómicas, en cambio, mueven 237/237. Así que la animación se
construye interpolando entre pares de poses que son las dos fases de un mismo
gesto — es movimiento anatómico real y completo, con las 271 mallas.

OTRO DETALLE QUE COSTÓ CARO
---------------------------
Desde Blender 4.4 las acciones tienen SLOTS. Asignar `animation_data.action` ya
no alcanza: sin enlazar `action_slot` la acción queda puesta pero ningún canal
se aplica. El horneado capturaba la pose de reposo y el resultado era basura.

POR QUÉ NO SE USA nla.bake
--------------------------
La primera versión horneaba con `bpy.ops.nla.bake(bake_types={"OBJECT"})` y el
resultado se veía mal por cuatro motivos, medidos sobre los GLB:

  - 0 de 271 mallas trasladaban. Cada hueso giraba sobre su propio origen en
    vez de seguir la cadena cinemática, así que se despegaban de la articulación.
  - saltos de 180° entre cuadros consecutivos: volteo de signo del cuaternión.
  - 128 mallas con la escala animada. Los huesos se inflaban.
  - canales mezclados de 2 y 49 claves: parte del rango no se muestreaba.

Como cada malla cuelga rígidamente de un hueso (`parent_type == 'BONE'`), su
`matrix_world` en cada cuadro ES la transformación rígida de ese hueso, ya
resuelta por la cinemática directa del rig. Así que se lee cuadro a cuadro y se
vuelca a curvas de objeto a mano: traslación correcta, sin escala, y con el
signo del cuaternión encadenado. Nada que estimar y nada que se pierda.

Uso:  python build_motion.py [--plan]
"""

import glob
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

import bpy
import mathutils

# Sin esto Blender headless bloquea los scripts embebidos del archivo.
bpy.context.preferences.filepaths.use_scripts_auto_execute = True

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", "app"))
PUBLIC = os.path.join(APP, "public", "anatomy", "motion")
URL_BASE = "/anatomy/motion"
GLTF_CLI = os.path.join(APP, "node_modules", ".bin",
                        "gltf-transform.cmd" if os.name == "nt" else "gltf-transform")

BLEND = os.environ["BIOMECH_BLEND"]

# Cuadros por tramo entre pose y pose. 24 da un gesto de 1 s a 24 fps.
SPAN = 24

# Umbral de la compuerta de calidad: giro máximo tolerado en un solo cuadro.
MAX_STEP_DEG = 30.0

# Cada secuencia es una lista de poses; se interpola de una a la siguiente y se
# vuelve al principio para que el bucle cierre.
SEQUENCES = [
    {
        "key": "pushup", "es": "Flexión de brazos", "en": "Push-up",
        "poses": ["Push up-up", "Push up-down"],
    },
    {
        "key": "yoga", "es": "Flexión y extensión", "en": "Flex and stretch",
        "poses": ["Yoga-stretch", "Yoga-flex"],
    },
    {
        "key": "foetal", "es": "Posición fetal", "en": "Foetal position",
        "poses": ["Anatomical position", "Foetal pose"],
    },
    {
        "key": "stance", "es": "Postura de marcha", "en": "Walking stance",
        "poses": ["Anatomical position", "Walk", "Relax"],
    },
]


def bind(obj, act):
    """Asigna la acción y ENLAZA EL SLOT (obligatorio desde Blender 4.4)."""
    ad = obj.animation_data or obj.animation_data_create()
    ad.action = act
    if hasattr(ad, "action_slot"):
        cands = (list(getattr(ad, "action_suitable_slots", []))
                 or list(getattr(act, "slots", [])))
        if cands:
            ad.action_slot = cands[0]
    return ad


def compress(src, dst):
    if not os.path.exists(GLTF_CLI):
        raise SystemExit(f"falta @gltf-transform/cli en {GLTF_CLI}")
    subprocess.run([GLTF_CLI, "draco", src, dst, "--quantize-position", "14"],
                   check=True, capture_output=True, shell=(os.name == "nt"))


def content_name(stem, path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return f"{stem}.{h.hexdigest()[:10]}.glb"


def skeleton_meshes():
    return [o for o in bpy.data.objects
            if o.type == "MESH" and o.parent and o.parent_type == "BONE"
            and len(o.data.polygons)]


def read_pose(arm, action):
    """Lee los canales de cada hueso con la pose aplicada.

    Sólo LEE. Escribir keyframes mientras la acción de la pose sigue asignada
    no sirve: `bind` reemplaza `animation_data.action`, así que cada pose
    borraba los keyframes de la anterior. Por eso primero se leen todas y
    después se escriben, con la acción ya desligada.
    """
    bind(arm, action)
    bpy.context.scene.frame_set(0)      # las poses viven en el cuadro 0
    bpy.context.view_layer.update()
    # Se guardan los canales tal como están, en el modo de rotación propio de
    # cada hueso. Probé pasar todo a cuaterniones vía matrix_basis pensando que
    # los volteos venían de interpolar euler cruzando ±180°: empeoró bastante
    # (foetal saltó de 12,6° a 164,9° entre cuadros). El rig depende de su modo
    # original, así que se respeta.
    return {pb.name: (pb.location.copy(), pb.rotation_quaternion.copy(),
                      pb.rotation_euler.copy(), pb.scale.copy())
            for pb in arm.pose.bones}


def write_keys(arm, snap, frame):
    """Vuelca una pose leída como keyframes en `frame`."""
    for pb in arm.pose.bones:
        v = snap.get(pb.name)
        if not v:
            continue
        pb.location, pb.rotation_quaternion, pb.rotation_euler, pb.scale = v
        pb.keyframe_insert("location", frame=frame)
        pb.keyframe_insert("scale", frame=frame)
        if pb.rotation_mode == "QUATERNION":
            pb.keyframe_insert("rotation_quaternion", frame=frame)
        else:
            pb.keyframe_insert("rotation_euler", frame=frame)


def main():
    plan = "--plan" in sys.argv
    if not plan:
        os.makedirs(PUBLIC, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=BLEND, use_scripts=True)
    disponibles = {a.name for a in bpy.data.actions}

    print("=== Secuencias ===")
    listas = []
    for spec in SEQUENCES:
        faltan = [p for p in spec["poses"] if p not in disponibles]
        if faltan:
            print(f"  {spec['key']:<8} faltan poses: {faltan}")
            continue
        n = len(spec["poses"]) * SPAN
        print(f"  {spec['key']:<8} {' -> '.join(spec['poses'])}  ({n} cuadros)")
        listas.append(spec)

    if plan:
        return

    catalog = {"clips": [], "attribution":
               "Z-Biomechanics / Z-Anatomy · CC BY-SA 4.0"}
    t0 = time.time()

    for spec in listas:
        print(f"\n--- {spec['key']} ---", flush=True)
        bpy.ops.wm.open_mainfile(filepath=BLEND, use_scripts=True)
        arm = bpy.data.objects["Armature"]
        meshes = skeleton_meshes()
        scn = bpy.context.scene

        # 1. Leer todas las poses (con la acción de cada una asignada).
        ciclo = spec["poses"] + [spec["poses"][0]]
        snaps = [read_pose(arm, bpy.data.actions[n]) for n in ciclo]

        # 2. Desligar y recién ahí escribir los keyframes en una acción propia.
        if arm.animation_data:
            arm.animation_data.action = None
        for i, snap in enumerate(snaps):
            write_keys(arm, snap, 1 + i * SPAN)

        f0, f1 = 1, 1 + (len(ciclo) - 1) * SPAN
        scn.frame_start, scn.frame_end = f0, f1

        # Comprobación: ¿las mallas se mueven de verdad?
        scn.frame_set(f0)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        p0 = {o.name: o.evaluated_get(dg).matrix_world.translation.copy()
              for o in meshes}
        scn.frame_set((f0 + f1) // 2)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        p1 = {o.name: o.evaluated_get(dg).matrix_world.translation.copy()
              for o in meshes}
        movidas = sum(1 for k in p0 if (p1[k] - p0[k]).length > 0.005)
        print(f"  mallas que se mueven: {movidas}/{len(meshes)}", flush=True)
        if movidas == 0:
            print("  !! la pose no mueve nada — se saltea", flush=True)
            continue

        # 3. Muestrear la transformada de mundo de cada malla, cuadro a cuadro.
        #
        #    Acá está la clave: cada malla cuelga rígidamente de un hueso, así
        #    que su matrix_world YA ES la transformación rígida de ese hueso, y
        #    la evalúa la cinemática directa del rig. No hay nada que estimar
        #    — sólo hay que leerla y volcarla sin romperla, que es exactamente
        #    lo que nla.bake no hacía: devolvía rotación sin traslación.
        frames = list(range(f0, f1 + 1))
        world = {o.name: [] for o in meshes}
        for f in frames:
            scn.frame_set(f)
            bpy.context.view_layer.update()
            dg = bpy.context.evaluated_depsgraph_get()
            for o in meshes:
                world[o.name].append(o.evaluated_get(dg).matrix_world.copy())
        print(f"  muestreados {len(frames)} cuadros x {len(meshes)} mallas",
              flush=True)

        # 4. Hornear la pose de reposo EN LOS VÉRTICES y dejar el objeto en la
        #    identidad.
        #
        #    Z-Anatomy espeja las piezas izquierda/derecha, así que sus matrices
        #    tienen determinante negativo. Descomponer una matriz espejada da
        #    escala negativa y un cuaternión ambiguo: de ahí los volteos de 170°.
        #    Metiendo el reposo en la malla y animando RELATIVO a él, el espejo
        #    aparece en ambos factores y se cancela — la transformada relativa
        #    es una rotación limpia, con determinante +1 y escala 1.
        scn.frame_set(f0)
        bpy.context.view_layer.update()
        rest = {}
        for o in meshes:
            rest[o.name] = world[o.name][0].copy()
            if o.data.users > 1:
                o.data = o.data.copy()      # no pisar mallas compartidas
            o.data.transform(rest[o.name])
            o.constraints.clear()
            o.parent = None
            o.matrix_world = mathutils.Matrix.Identity(4)
            o.animation_data_clear()

        for o in list(bpy.data.objects):
            if o not in meshes:
                bpy.data.objects.remove(o, do_unlink=True)

        # 5. Escribir las curvas: sólo posición y rotación.
        #
        #    La escala NUNCA se keyframea. Un hueso no cambia de tamaño, y el
        #    horneado anterior le animaba la escala a 128 mallas.
        #
        #    Y se fuerza continuidad de signo en el cuaternión: q y -q son la
        #    misma orientación, pero si el signo salta entre cuadros el slerp
        #    toma el camino largo y el hueso pega una vuelta entera. Ese era el
        #    salto de 180° entre cuadros consecutivos que medimos.
        flips = 0
        worst_scale = 0.0
        worst_step = 0.0        # mayor giro entre dos cuadros seguidos
        for o in meshes:
            o.rotation_mode = "QUATERNION"
            inv_rest = rest[o.name].inverted()
            prev = None
            for i, f in enumerate(frames):
                rel = world[o.name][i] @ inv_rest
                loc, quat, scale = rel.decompose()
                # Con el reposo cancelado esto tiene que ser ~1 en los tres ejes.
                worst_scale = max(worst_scale, max(abs(s - 1.0) for s in scale))
                if prev is not None:
                    if quat.dot(prev) < 0.0:
                        quat.negate()
                        flips += 1
                    step = math.degrees(2 * math.acos(
                        min(1.0, abs(quat.dot(prev)))))
                    worst_step = max(worst_step, step)
                prev = quat.copy()
                o.location = loc
                o.rotation_quaternion = quat
                o.keyframe_insert("location", frame=f)
                o.keyframe_insert("rotation_quaternion", frame=f)
        print(f"  signos corregidos: {flips}; desvío de escala máx: "
              f"{worst_scale:.4f}; salto máx entre cuadros: {worst_step:.1f}°",
              flush=True)

        # Compuerta de calidad. Un hueso que gira más de 30° en un cuadro no es
        # movimiento anatómico: es el rig evaluándose mal. Los drivers de
        # Z-Biomechanics llaman funciones que registra el addon de Z-Anatomy, y
        # bpy headless no lo carga (`NameError: name 'test' is not defined` en
        # el log), así que parte de las poses sale corrupta. Mejor publicar
        # menos clips y que los que salgan estén sanos.
        if worst_step > MAX_STEP_DEG:
            print(f"  !! descartado: {worst_step:.0f}° > {MAX_STEP_DEG}° por cuadro",
                  flush=True)
            continue

        # El GLB queda en metros y en Y-up (export_yup): la app aplica la
        # escala a milímetros con un grupo padre y NO lo rota.
        tmp = tempfile.mkdtemp()
        plain, packed = os.path.join(tmp, "a.glb"), os.path.join(tmp, "b.glb")
        bpy.ops.export_scene.gltf(
            filepath=plain, export_format="GLB",
            export_animations=True, export_frame_range=True,
            export_apply=True, export_yup=True,
            export_cameras=False, export_lights=False,
        )
        compress(plain, packed)
        for old in glob.glob(os.path.join(PUBLIC, f"{spec['key']}.*.glb")):
            os.remove(old)
        fname = content_name(spec["key"], packed)
        shutil.move(packed, os.path.join(PUBLIC, fname))
        shutil.rmtree(tmp, ignore_errors=True)
        nbytes = os.path.getsize(os.path.join(PUBLIC, fname))

        catalog["clips"].append({
            "key": spec["key"], "es": spec["es"], "en": spec["en"],
            "file": f"{URL_BASE}/{fname}", "bytes": nbytes,
            "frames": f1 - f0, "meshes": len(meshes),
            "poses": spec["poses"],
        })
        print(f"  {nbytes / 1024 / 1024:.2f} MB  ({time.time() - t0:.0f}s)", flush=True)

    with open(os.path.join(PUBLIC, "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, ensure_ascii=False)

    total = sum(c["bytes"] for c in catalog["clips"])
    print(f"\n=== Resumen ===")
    print(f"  clips  : {len(catalog['clips'])}")
    print(f"  total  : {total / 1024 / 1024:.2f} MB")
    print(f"  tiempo : {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
