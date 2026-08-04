"""
Z-Biomechanics -> GLB animados.

Estrategia. Las 271 mallas del esqueleto estan emparentadas a un hueso
(parent_type='BONE'), no deformadas por skinning — que es lo correcto, un hueso
es rigido. Ademas la armadura mueve todo con 153 restricciones de limite de
rotacion y 89 de copia, y las restricciones NO viajan en glTF.

Asi que en vez de exportar armadura + skin, se hornea el movimiento a
transformaciones de objeto: para cada cuadro se toma la matriz de mundo
resultante de cada malla y se convierte en keyframes propios. Despues se
desemparenta y se exporta. glTF anima nodos de forma nativa y three.js lo
reproduce con AnimationMixer sin nada especial.

Uso:  python build_motion.py [--plan] [--only Walk1,Jog]
"""

import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", "app"))
PUBLIC = os.path.join(APP, "public", "anatomy", "motion")
URL_BASE = "/anatomy/motion"
GLTF_CLI = os.path.join(APP, "node_modules", ".bin",
                        "gltf-transform.cmd" if os.name == "nt" else "gltf-transform")

BLEND = os.environ["BIOMECH_BLEND"]

# Misma similitud que el resto del proyecto: Z-Anatomy esta en metros.
SCALE = 968.3

# Que movimientos exportar. Los de 0..0 cuadros son poses fijas, no animaciones.
CLIPS = [
    ("walk", "Walk 1", "Marcha", "Walk"),
    ("jog", "Run/Jog", "Trote", "Jog"),
    ("rom", "Range of motions", "Rango articular", "Range of motion"),
    ("pushup", "Jumps (2)", "Salto", "Jump"),
]

# Un cuadro de cada N: 30 fps es innecesario para estudiar un gesto.
FRAME_STEP = 2


def compress(src, dst):
    if not os.path.exists(GLTF_CLI):
        raise SystemExit(f"falta @gltf-transform/cli en {GLTF_CLI}")
    subprocess.run(
        [GLTF_CLI, "draco", src, dst, "--quantize-position", "14"],
        check=True, capture_output=True, shell=(os.name == "nt"))


def content_name(stem, path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return f"{stem}.{h.hexdigest()[:10]}.glb"


def scene_meshes():
    """Mallas emparentadas a un hueso: son las que se mueven."""
    return [o for o in bpy.data.objects
            if o.type == "MESH" and o.parent and o.parent_type == "BONE"
            and len(o.data.polygons)]


def main():
    plan = "--plan" in sys.argv
    only = None
    for a in sys.argv:
        if a.startswith("--only"):
            only = set(a.split("=", 1)[1].split(",")) if "=" in a else None

    print(f"Abriendo {os.path.basename(BLEND)}…", flush=True)
    bpy.ops.wm.open_mainfile(filepath=BLEND)

    arm = bpy.data.objects.get("Armature")
    if not arm:
        raise SystemExit("no está la armadura 'Armature'")

    meshes = scene_meshes()
    tris = sum(len(o.data.polygons) for o in meshes)
    print(f"Mallas del esqueleto : {len(meshes)}  ({tris:,} triángulos)")
    print(f"Huesos               : {len(arm.data.bones)}")

    acts = {a.name: a for a in bpy.data.actions}
    print("\n=== Clips a exportar ===")
    plan_rows = []
    for key, action_name, es, en in CLIPS:
        a = acts.get(action_name)
        if not a:
            print(f"  {key:<8} FALTA la acción '{action_name}'")
            continue
        f0, f1 = int(a.frame_range[0]), int(a.frame_range[1])
        n = max(1, (f1 - f0) // FRAME_STEP + 1)
        print(f"  {key:<8} '{action_name}'  cuadros {f0}..{f1}  "
              f"-> {n} muestras")
        plan_rows.append((key, action_name, es, en, f0, f1))

    if plan:
        return

    os.makedirs(PUBLIC, exist_ok=True)
    catalog = {"clips": [], "attribution":
               "Z-Biomechanics / Z-Anatomy · CC BY-SA 4.0"}
    t0 = time.time()

    for key, action_name, es, en, f0, f1 in plan_rows:
        if only and key not in only:
            continue
        print(f"\n--- {key} ---", flush=True)

        # Recargar limpio: hornear modifica la escena de forma irreversible.
        bpy.ops.wm.open_mainfile(filepath=BLEND)
        arm = bpy.data.objects["Armature"]
        meshes = scene_meshes()

        act = bpy.data.actions[action_name]
        if not arm.animation_data:
            arm.animation_data_create()
        arm.animation_data.action = act

        scn = bpy.context.scene
        scn.frame_start, scn.frame_end = f0, f1

        # Hornear a transformaciones de objeto. visual_keying captura el
        # resultado de las restricciones; clear_parents corta el vínculo al
        # hueso y deja cada malla con su propia animación.
        for o in bpy.data.objects:
            o.select_set(False)
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]

        print(f"  horneando {len(meshes)} mallas, cuadros {f0}..{f1}…", flush=True)
        bpy.ops.nla.bake(
            frame_start=f0, frame_end=f1, step=FRAME_STEP,
            only_selected=True, visual_keying=True,
            clear_constraints=True, clear_parents=True,
            bake_types={"OBJECT"},
        )

        # Quitar todo lo que no sea la malla horneada.
        for o in list(bpy.data.objects):
            if o not in meshes:
                bpy.data.objects.remove(o, do_unlink=True)

        # Pasar a milímetros, como el resto del proyecto.
        for o in meshes:
            o.scale = (o.scale[0] * SCALE, o.scale[1] * SCALE, o.scale[2] * SCALE)
            o.location = (o.location[0] * SCALE, o.location[1] * SCALE,
                          o.location[2] * SCALE)

        tmp = tempfile.mkdtemp()
        plain = os.path.join(tmp, "a.glb")
        bpy.ops.export_scene.gltf(
            filepath=plain, export_format="GLB",
            export_animations=True, export_frame_range=True,
            export_apply=True, export_yup=True,
            export_materials="EXPORT", export_cameras=False,
            export_lights=False,
        )
        raw = os.path.getsize(plain)

        packed = os.path.join(tmp, "b.glb")
        compress(plain, packed)
        for old in glob.glob(os.path.join(PUBLIC, f"{key}.*.glb")):
            os.remove(old)
        fname = content_name(key, packed)
        shutil.move(packed, os.path.join(PUBLIC, fname))
        shutil.rmtree(tmp, ignore_errors=True)
        nbytes = os.path.getsize(os.path.join(PUBLIC, fname))

        catalog["clips"].append({
            "key": key, "es": es, "en": en,
            "file": f"{URL_BASE}/{fname}", "bytes": nbytes,
            "frames": f1 - f0, "meshes": len(meshes),
        })
        print(f"  {raw / 1024 / 1024:.1f} MB -> {nbytes / 1024 / 1024:.2f} MB "
              f"({time.time() - t0:.0f}s)", flush=True)

    with open(os.path.join(PUBLIC, "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, ensure_ascii=False)

    total = sum(c["bytes"] for c in catalog["clips"])
    print(f"\n=== Resumen ===")
    print(f"  clips  : {len(catalog['clips'])}")
    print(f"  total  : {total / 1024 / 1024:.2f} MB")
    print(f"  tiempo : {time.time() - t0:.0f}s")
    print(f"  salida : {PUBLIC}")


if __name__ == "__main__":
    main()
