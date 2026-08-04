"""
Z-Anatomy -> chunks GLB por region x capa, alineados con BodyParts3D.

Las dos fuentes son el MISMO cuerpo escaneado: emparejando 9 huesos grandes y
ajustando una similitud, el residuo queda en 0,5 mm de mediana. Por eso:

  - se aplica esa transformacion (escala + traslacion) y ambas fuentes quedan
    en el mismo espacio, intercambiables y combinables
  - la region de cada malla se HEREDA de la estructura mas cercana de
    BodyParts3D (out/region_map.json) en vez de re-derivarla de las colecciones
    de Blender, que se solapan a proposito

Uso:  python build_zanatomy.py [--plan]
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
from collections import defaultdict

import bpy
import numpy as np
import trimesh
import fast_simplification
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
APP = os.path.abspath(os.path.join(HERE, "..", "app"))
PUBLIC = os.path.join(APP, "public", "anatomy", "zanatomy")
GLTF_CLI = os.path.join(APP, "node_modules", ".bin",
                        "gltf-transform.cmd" if os.name == "nt" else "gltf-transform")

trimesh.util.log.setLevel("ERROR")

# Similitud medida en measure_registration.py (9 huesos, residuo 0,5 mm).
SCALE = 968.3
OFFSET = np.array([-0.4, -98.0, -13.1])

# Colecciones de Z-Anatomy -> capas de la app. El orden importa: las
# colecciones se solapan (los nervios listan los musculos que inervan), asi que
# la primera que matchea define la capa.
COLLECTION_LAYER = [
    ("skeletal", "1: Skeletal system"),
    ("joints", "3: Joints"),
    ("insertions", "2: Muscular insertions"),
    ("muscular", "4: Muscular system"),
    ("vascular", "5: Cardiovascular system"),
    ("lymphoid", "6: Lymphoid organs"),
    ("organs", "8: Visceral systems"),
    ("nervous", "7: Nervous system & Sense organs"),
]

LAYER_ORDER = ["skeletal", "joints", "insertions", "organs", "lymphoid",
               "vascular", "nervous", "muscular"]

LAYER_LABEL = {
    "skeletal": "Huesos", "joints": "Articulaciones",
    "insertions": "Inserciones", "organs": "Órganos",
    "lymphoid": "Linfoide", "vascular": "Vasos",
    "nervous": "Nervios", "muscular": "Músculos",
}

LAYER_COLOR = {
    "skeletal": [0.91, 0.89, 0.82, 1.0],
    "joints": [0.62, 0.74, 0.80, 1.0],
    "insertions": [0.85, 0.62, 0.42, 1.0],
    "organs": [0.72, 0.45, 0.40, 1.0],
    "lymphoid": [0.55, 0.68, 0.55, 1.0],
    "vascular": [0.69, 0.15, 0.18, 1.0],
    "nervous": [0.95, 0.86, 0.55, 1.0],
    "muscular": [0.70, 0.25, 0.23, 1.0],
}

REGION_LABEL = {
    "head": "Cabeza", "neck": "Cuello", "thorax": "Tórax",
    "abdomen": "Abdomen", "back": "Espalda",
    "upperlimb": "Miembro superior", "lowerlimb": "Miembro inferior",
}

REGION_BUDGET = 900_000
OVERVIEW_BUDGET = 550_000
MIN_FACES = 40

# El sufijo .g marca los TITULOS de cada coleccion, que Z-Anatomy incluye como
# texto 3D al costado del modelo ('Skeletal system.g', 'Muscular system.g'...).
# Son 11 y aparecen flotando junto al cuerpo si no se filtran.
LABEL_SUFFIX = ".g"
# Red de seguridad por si aparece otro tipo de anotacion: el cuerpo es simetrico
# en X y no pasa de ~0,25 a cada lado; los rotulos viven en X = -1.
BODY_X_LIMIT = -0.45


# ── utilidades compartidas con el pipeline de BodyParts3D ────────────
def decimate(mesh, target):
    n = len(mesh.faces)
    if n <= target or target < 4:
        return mesh
    v, f = fast_simplification.simplify(
        np.ascontiguousarray(mesh.vertices, dtype=np.float32),
        np.ascontiguousarray(mesh.faces, dtype=np.uint32),
        1.0 - target / n,
    )
    return trimesh.Trimesh(vertices=v, faces=f, process=False)


def compress(src, dst):
    # Sin Draco los assets pesan ~6x mas. Antes esto caia a copiar en silencio
    # y el error solo se notaba mirando los megabytes al final: mejor fallar.
    if not os.path.exists(GLTF_CLI):
        raise SystemExit(
            f"falta @gltf-transform/cli en {GLTF_CLI}\n"
            f"  instalalo con:  pnpm --dir app add -D @gltf-transform/cli"
        )
    subprocess.run([GLTF_CLI, "draco", src, dst, "--quantize-position", "14"],
                   check=True, capture_output=True, shell=(os.name == "nt"))


def content_name(stem, path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return f"{stem}.{h.hexdigest()[:10]}.glb"


def export_chunk(pieces, stem, center, layer):
    scene = trimesh.Scene()
    entries, tris = [], 0
    lo = np.array([np.inf] * 3)
    hi = np.array([-np.inf] * 3)

    for zid, name, mesh in pieces:
        m = mesh.copy()
        m.apply_translation(-center)
        lo = np.minimum(lo, m.bounds[0])
        hi = np.maximum(hi, m.bounds[1])
        m.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                name=layer,
                baseColorFactor=LAYER_COLOR.get(layer, [0.8, 0.8, 0.8, 1.0]),
                metallicFactor=0.0, roughnessFactor=0.62,
            )
        )
        scene.add_geometry(m, node_name=zid, geom_name=zid)
        entries.append({"fma": zid, "name": name, "faces": len(m.faces)})
        tris += len(m.faces)

    tmp = tempfile.mkdtemp()
    plain, packed = os.path.join(tmp, "a.glb"), os.path.join(tmp, "b.glb")
    scene.export(plain, include_normals=True)
    compress(plain, packed)
    for old in glob.glob(os.path.join(PUBLIC, f"{stem}.*.glb")):
        os.remove(old)
    fname = content_name(stem, packed)
    shutil.move(packed, os.path.join(PUBLIC, fname))
    shutil.rmtree(tmp, ignore_errors=True)

    bounds = None if not np.isfinite(lo).all() else {
        "min": [round(float(v), 1) for v in lo],
        "max": [round(float(v), 1) for v in hi],
    }
    return fname, os.path.getsize(os.path.join(PUBLIC, fname)), tris, entries, bounds


# ── extraccion desde Blender ─────────────────────────────────────────
def extract(obj):
    """Objeto de Blender -> Trimesh en el espacio de BodyParts3D (milimetros).

    Se evalua el objeto con sus modificadores aplicados; varias mallas de
    Z-Anatomy usan Solidify o Curve y sin evaluar salen vacias o planas.
    """
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    if not me or not len(me.polygons):
        if me:
            ev.to_mesh_clear()
        return None

    me.calc_loop_triangles()
    mw = obj.matrix_world
    verts = np.array([(mw @ v.co)[:] for v in me.vertices], dtype=np.float64)
    faces = np.array([t.vertices[:] for t in me.loop_triangles], dtype=np.int64)
    ev.to_mesh_clear()

    if not len(faces):
        return None

    verts = verts * SCALE + OFFSET
    m = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    m.merge_vertices()
    return m


def main():
    with open(os.path.join(OUT, "region_map.json"), encoding="utf-8") as fh:
        ref = json.load(fh)
    ref_pts = np.array([s["c"] for s in ref["structures"]], dtype=np.float64)
    ref_reg = [s["region"] for s in ref["structures"]]
    center = np.array(ref["center"], dtype=np.float64)
    print(f"Referencia: {len(ref_pts)} estructuras de BodyParts3D", flush=True)

    print("Abriendo Z-Anatomy…", flush=True)
    bpy.ops.wm.open_mainfile(filepath=os.environ["ZANATOMY_BLEND"])

    # Capa de cada objeto, por prioridad de coleccion.
    layer_of = {}
    for key, colname in COLLECTION_LAYER:
        col = next((c for c in bpy.data.collections if c.name == colname), None)
        if not col:
            print(f"  aviso: falta la coleccion {colname}")
            continue
        for o in col.all_objects:
            if o.type == "MESH" and len(o.data.polygons):
                layer_of.setdefault(o.name, key)

    todas = [o for o in bpy.data.objects
             if o.type == "MESH" and len(o.data.polygons) and o.name in layer_of]

    objs, rotulos = [], []
    for o in todas:
        if o.name.endswith(LABEL_SUFFIX):
            rotulos.append(o.name)
            continue
        # Chequeo espacial: cualquier cosa muy a la izquierda del cuerpo es
        # anotacion, no anatomia.
        xs = [(o.matrix_world @ Vector(c))[0] for c in o.bound_box]
        if max(xs) < BODY_X_LIMIT:
            rotulos.append(o.name)
            continue
        objs.append(o)

    print(f"Mallas con capa : {len(todas)}", flush=True)
    print(f"  rotulos 3D descartados : {len(rotulos)}", flush=True)
    for r in rotulos[:12]:
        print(f"      {r}", flush=True)
    print(f"  anatomia a exportar    : {len(objs)}", flush=True)

    # Identificadores estables y a prueba de saneado. El GLTFLoader de three
    # pasa los nombres por PropertyBinding.sanitizeNodeName, que convierte los
    # espacios en '_' y ELIMINA . : / [ ]. Con nombres como
    # 'Clavicular head of pectoralis major muscle.l' el nombre que queda en la
    # escena no coincide con el del catalogo y la seleccion no encuentra nada.
    # El indice va sobre la lista ordenada para que no cambie entre builds.
    zid_of = {o.name: f"Z{i:05d}" for i, o in enumerate(sorted(objs, key=lambda x: x.name))}

    print("Extrayendo geometria y asignando region…", flush=True)
    t0 = time.time()
    items = []
    for i, o in enumerate(objs):
        m = extract(o)
        if m is None or not len(m.faces):
            continue
        c = (m.bounds[0] + m.bounds[1]) / 2
        # Region heredada de la estructura mas cercana de BodyParts3D.
        d = np.linalg.norm(ref_pts - c, axis=1)
        items.append((zid_of[o.name], o.name, layer_of[o.name],
                      ref_reg[int(d.argmin())], m))
        if (i + 1) % 400 == 0:
            print(f"  {i + 1}/{len(objs)}  ({time.time() - t0:.0f}s)", flush=True)

    print(f"Extraidas {len(items)} mallas en {time.time() - t0:.0f}s", flush=True)

    by_region = defaultdict(lambda: defaultdict(list))
    for zid, name, layer, region, mesh in items:
        by_region[region][layer].append((zid, name, mesh))

    print("\n=== Plan: mallas por region x capa ===", flush=True)
    hdr = f"{'region':<18}" + "".join(f"{k[:9]:>11}" for k in LAYER_ORDER) + f"{'total':>8}"
    print(hdr, flush=True)
    print("-" * len(hdr), flush=True)
    for region in REGION_LABEL:
        row = by_region.get(region, {})
        cells = "".join(f"{len(row.get(k, [])):>11}" for k in LAYER_ORDER)
        print(f"{REGION_LABEL[region]:<18}{cells}{sum(len(v) for v in row.values()):>8}",
              flush=True)

    if "--plan" in sys.argv:
        return

    os.makedirs(PUBLIC, exist_ok=True)
    catalog = {
        "layers": [{"key": k, "label": LAYER_LABEL[k]} for k in LAYER_ORDER],
        "regions": [], "overview": None,
        "attribution": "Z-Anatomy · CC BY-SA 4.0 · derivado de BodyParts3D "
                       "© The Database Center for Life Science, CC BY-SA 2.1 JP",
    }

    overview_pool = []
    grand_bytes = grand_tris = 0
    t0 = time.time()

    for region, label in REGION_LABEL.items():
        layers = by_region.get(region)
        if not layers:
            continue
        raw_tot = sum(len(m.faces) for lst in layers.values() for _, _, m in lst)
        entry = {"key": region, "label": label, "layers": {}}
        rlo = np.array([np.inf] * 3)
        rhi = np.array([-np.inf] * 3)
        rbytes = rtris = 0

        for lk in LAYER_ORDER:
            lst = layers.get(lk)
            if not lst:
                continue
            raw = sum(len(m.faces) for _, _, m in lst)
            budget = max(15_000, int(REGION_BUDGET * raw / max(raw_tot, 1)))
            ratio = min(1.0, budget / max(raw, 1))
            pieces = []
            for zid, name, mesh in lst:
                d = decimate(mesh, max(MIN_FACES, int(len(mesh.faces) * ratio)))
                pieces.append((zid, name, d))
                if len(d.faces) > MIN_FACES:
                    overview_pool.append((zid, name, lk, d))

            fname, nbytes, tris, entries, bnd = export_chunk(
                pieces, f"{region}__{lk}", center, lk)
            entry["layers"][lk] = {
                "file": f"/anatomy/zanatomy/{fname}", "bytes": nbytes,
                "tris": tris, "structures": entries,
            }
            if bnd:
                rlo = np.minimum(rlo, bnd["min"])
                rhi = np.maximum(rhi, bnd["max"])
            rbytes += nbytes
            rtris += tris

        entry["bounds"] = {
            "min": [round(float(v), 1) for v in rlo],
            "max": [round(float(v), 1) for v in rhi],
        }
        catalog["regions"].append(entry)
        grand_bytes += rbytes
        grand_tris += rtris
        print(f"  {label:<18}{rtris:>9,} tris  {rbytes / 1024 / 1024:>6.2f} MB  "
              f"({time.time() - t0:.0f}s)", flush=True)

    # ── overview ─────────────────────────────────────────────────────
    print("\nGenerando vista de cuerpo entero…", flush=True)
    raw_ov = sum(len(m.faces) for _, _, _, m in overview_pool)
    ratio = min(1.0, OVERVIEW_BUDGET / max(raw_ov, 1))
    ov = defaultdict(list)
    for zid, name, lk, mesh in overview_pool:
        d = decimate(mesh, max(20, int(len(mesh.faces) * ratio)))
        if len(d.faces) >= 10:
            ov[lk].append((zid, name, d))

    catalog["overview"] = {"layers": {}}
    olo = np.array([np.inf] * 3)
    ohi = np.array([-np.inf] * 3)
    for lk, pieces in ov.items():
        fname, nbytes, tris, entries, bnd = export_chunk(
            pieces, f"overview__{lk}", center, lk)
        catalog["overview"]["layers"][lk] = {
            "file": f"/anatomy/zanatomy/{fname}", "bytes": nbytes,
            "tris": tris, "structures": entries,
        }
        if bnd:
            olo = np.minimum(olo, bnd["min"])
            ohi = np.maximum(ohi, bnd["max"])
        grand_bytes += nbytes
        print(f"  overview/{lk:<12}{tris:>8,} tris  {nbytes / 1024 / 1024:>6.2f} MB",
              flush=True)
    catalog["overview"]["bounds"] = {
        "min": [round(float(v), 1) for v in olo],
        "max": [round(float(v), 1) for v in ohi],
    }

    with open(os.path.join(PUBLIC, "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, ensure_ascii=False)

    n = sum(len(l["structures"]) for r in catalog["regions"] for l in r["layers"].values())
    print("\n=== Resumen ===", flush=True)
    print(f"  regiones      : {len(catalog['regions'])}", flush=True)
    print(f"  estructuras   : {n}", flush=True)
    print(f"  triangulos    : {grand_tris:,}", flush=True)
    print(f"  total en disco: {grand_bytes / 1024 / 1024:.1f} MB", flush=True)
    print(f"  tiempo        : {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
