"""
Construye el cuerpo completo: 934 mallas -> chunks GLB por region x capa.

Modelo de carga de la app:
  - un chunk "overview" de cuerpo entero en LOD bajo (vista inicial)
  - por region, un GLB por capa; se pide solo la region que el usuario mira

Asignacion:
  capa    -> ontologia FMA (sistemas raiz), sin solapamiento
  region  -> ontologia por prioridad (primera que matchea gana);
             las que no matchean se asignan por posicion del centroide
  piel    -> malla unica de cuerpo entero, recortada a la caja de cada region

Uso:  python build_fullbody.py [--plan]
"""

import csv
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict, deque

import numpy as np
import trimesh
import fast_simplification

RAW = os.environ["BP3D_RAW"]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
STL = os.path.join(RAW, "stl")
APP = os.path.abspath(os.path.join(HERE, "..", "app"))
PUBLIC = os.path.join(APP, "public", "anatomy", "bodyparts3d")
GLTF_CLI = os.path.join(APP, "node_modules", ".bin",
                        "gltf-transform.cmd" if os.name == "nt" else "gltf-transform")

trimesh.util.log.setLevel("ERROR")

# --- Capas: sistemas raiz de FMA ------------------------------------------
LAYERS = {
    "skin":     ("FMA72979", "Piel"),
    "vascular": ("FMA7161",  "Vasos"),
    "muscular": ("FMA72954", "Músculos"),
    "skeletal": ("FMA23881", "Huesos"),
    "nervous":  ("FMA7157",  "Sistema nervioso"),
}
# Los sistemas viscerales se agrupan en una sola capa "organos".
ORGAN_ROOTS = {
    "FMA7158": "respiratorio", "FMA7152": "digestivo", "FMA7159": "urinario",
    "FMA7160": "reproductor", "FMA9668": "endocrino", "FMA74594": "linfático",
    "FMA78499": "órganos de los sentidos",
}
LAYER_ORDER = ["skeletal", "organs", "vascular", "nervous", "muscular", "skin"]
LAYER_LABEL = {**{k: v[1] for k, v in LAYERS.items()}, "organs": "Órganos"}

LAYER_COLOR = {
    "skin":     [0.92, 0.76, 0.66, 1.0],
    "muscular": [0.70, 0.25, 0.23, 1.0],
    "vascular": [0.69, 0.15, 0.18, 1.0],
    "skeletal": [0.91, 0.89, 0.82, 1.0],
    "nervous":  [0.95, 0.86, 0.55, 1.0],
    "organs":   [0.72, 0.45, 0.40, 1.0],
}

# --- Regiones: orden de prioridad (la primera que matchea gana) ------------
REGIONS = [
    ("head",      "FMA7154",  "Cabeza",           True),
    ("neck",      "FMA7155",  "Cuello",           True),
    ("thorax",    "FMA9576",  "Tórax",            True),
    ("abdomen",   "FMA9577",  "Abdomen",          True),
    # 'pelvis' (FMA9578) se omite: sus estructuras quedan absorbidas por
    # abdomen y miembro inferior segun la prioridad, y el chunk sale vacio.
    ("back",      "FMA14181", "Espalda",          False),
    ("upperlimb", "FMA7183",  "Miembro superior", True),
    ("lowerlimb", "FMA7184",  "Miembro inferior", True),
]

# Presupuesto de triangulos por region (todas sus capas juntas).
REGION_BUDGET = 900_000
OVERVIEW_BUDGET = 550_000
MIN_FACES = 48


def read_tsv(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        r = csv.reader(fh, delimiter="\t")
        next(r, None)
        for row in r:
            if row:
                yield row


def build_graph():
    """Jerarquia SOLO desde conventional_part_of.

    composite_parts.txt define agrupaciones ("conjunto de falanges" -> cada
    falange), no pertenencia anatomica. Incluirlo mete las falanges del pie
    dentro de 'miembro superior' y rompe las cajas de region.
    """
    children = defaultdict(set)
    names = {}
    for row in read_tsv(os.path.join(RAW, "conventional_part_of.txt")):
        if len(row) >= 4:
            children[row[0]].add(row[2])
    for row in read_tsv(os.path.join(RAW, "parts_list_e.txt")):
        if len(row) >= 2:
            names[row[0]] = row[1]
    return children, names


def desc(children, root, names=None, skip_groups=False):
    """Descendientes de `root`.

    Con skip_groups=True no se desciende por nodos de agrupacion ("set of ...").
    Son colecciones genericas, no partes anatomicas: 'set of phalanges' cuelga
    del esqueleto del miembro superior pero contiene tambien las falanges del
    pie, y arrastra 28 estructuras del pie al brazo. Lo que queda sin asignar
    se resuelve despues por posicion, que es mas confiable que la ontologia.
    """
    seen, q = set(), deque([root])
    while q:
        node = q.popleft()
        for c in children.get(node, ()):
            if c in seen:
                continue
            seen.add(c)
            if skip_groups and names and names.get(c, "").startswith("set of "):
                continue  # se cuenta, pero no se desciende
            q.append(c)
    return seen


def load_mesh(fma):
    m = trimesh.load(os.path.join(STL, fma + ".stl"), process=False, force="mesh")
    m.merge_vertices()  # los STL son triangle soup: sin soldar no hay decimacion
    return m


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


def clip_box(mesh, lo, hi, pad=15.0):
    planes = [
        ([1, 0, 0], [lo[0] - pad, 0, 0]), ([-1, 0, 0], [hi[0] + pad, 0, 0]),
        ([0, 1, 0], [0, lo[1] - pad, 0]), ([0, -1, 0], [0, hi[1] + pad, 0]),
        ([0, 0, 1], [0, 0, lo[2] - pad]), ([0, 0, -1], [0, 0, hi[2] + pad]),
    ]
    for normal, origin in planes:
        if len(mesh.faces) == 0:
            return mesh
        mesh = mesh.slice_plane(plane_origin=origin, plane_normal=normal, cap=False)
    return mesh


def compress(src, dst):
    if not os.path.exists(GLTF_CLI):
        shutil.copyfile(src, dst)
        return
    subprocess.run([GLTF_CLI, "draco", src, dst, "--quantize-position", "14"],
                   check=True, capture_output=True, shell=(os.name == "nt"))


def content_name(stem, path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return f"{stem}.{h.hexdigest()[:10]}.glb"


def export_chunk(pieces, stem, center):
    """pieces: lista de (fma, name, Trimesh ya decimada).

    Devuelve (fname, bytes, tris, entries, bounds). `bounds` son los limites reales
    del chunk YA centrado: todas las regiones comparten un mismo origen global para
    que encajen entre si, asi que el visor necesita estos limites para apuntar la
    camara a la region correcta en vez de al centro del cuerpo.
    """
    scene = trimesh.Scene()
    entries, tris = [], 0
    lo = np.array([np.inf] * 3)
    hi = np.array([-np.inf] * 3)
    for fma, name, mesh in pieces:
        m = mesh.copy()
        m.apply_translation(-center)
        lo = np.minimum(lo, m.bounds[0])
        hi = np.maximum(hi, m.bounds[1])
        layer = stem.split("__")[-1]
        m.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                name=layer,
                baseColorFactor=LAYER_COLOR.get(layer, [0.8, 0.8, 0.8, 1.0]),
                metallicFactor=0.0, roughnessFactor=0.62,
            )
        )
        scene.add_geometry(m, node_name=fma, geom_name=fma)
        entries.append({"fma": fma, "name": name, "faces": len(m.faces)})
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


def main():
    children, names = build_graph()
    stl_ids = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(STL, "*.stl")))
    print(f"Mallas en disco: {len(stl_ids)}\n", flush=True)

    # --- capa de cada malla ------------------------------------------------
    layer_of = {}
    for key, (root, _) in LAYERS.items():
        for m in desc(children, root):
            layer_of.setdefault(m, key)
    for root in ORGAN_ROOTS:
        for m in desc(children, root):
            layer_of.setdefault(m, "organs")

    # --- region de cada malla (prioridad ontologica, sin nodos de grupo) ---
    region_of = {}
    region_sets = {key: desc(children, root, names, skip_groups=True)
                   for key, root, _, _ in REGIONS}
    for key, _, _, _ in REGIONS:
        for m in region_sets[key]:
            region_of.setdefault(m, key)

    assigned = [m for m in stl_ids if m in layer_of]
    print(f"con capa   : {len(assigned)}/{len(stl_ids)}", flush=True)
    print(f"con region : {sum(1 for m in assigned if m in region_of)}", flush=True)

    # --- cajas por region, a partir de lo ya asignado ----------------------
    print("\nCalculando cajas de region...", flush=True)
    boxes, members = {}, defaultdict(list)
    for m in assigned:
        if m in region_of and layer_of[m] != "skin":
            members[region_of[m]].append(m)

    bounds_cache = {}
    for key, _, label, _ in REGIONS:
        bs = []
        for m in members.get(key, []):
            b = load_mesh(m).bounds
            bounds_cache[m] = b
            bs.append(b)
        if bs:
            a = np.array(bs)
            # Percentiles en vez de min/max: el dataset tiene errores de
            # clasificacion sueltos y una sola malla mal ubicada arruinaria
            # el recorte de la piel para toda la region.
            lo = np.percentile(a[:, 0, :], 2, axis=0)
            hi = np.percentile(a[:, 1, :], 98, axis=0)
            hard_lo, hard_hi = a[:, 0, :].min(axis=0), a[:, 1, :].max(axis=0)
            boxes[key] = (lo, hi)
            drift = max(np.max(lo - hard_lo), np.max(hard_hi - hi))
            flag = f"  (recortado {drift:.0f}mm)" if drift > 40 else ""
            print(f"  {label:<18} {len(bs):>4} mallas  "
                  f"Z {lo[2]:7.0f}..{hi[2]:7.0f}{flag}", flush=True)

    # --- huerfanos: asignacion espacial por centroide ----------------------
    orphans = [m for m in assigned if m not in region_of]
    print(f"\nAsignando {len(orphans)} huerfanos por posicion...", flush=True)
    for m in orphans:
        b = bounds_cache.get(m) or load_mesh(m).bounds
        c = (b[0] + b[1]) / 2
        best, bestd = None, 1e18
        for key, (lo, hi) in boxes.items():
            ctr = (lo + hi) / 2
            inside = np.all(c >= lo - 20) and np.all(c <= hi + 20)
            d = np.linalg.norm(c - ctr) - (1e6 if inside else 0)
            if d < bestd:
                best, bestd = key, d
        region_of[m] = best

    counts = defaultdict(lambda: defaultdict(int))
    for m in assigned:
        counts[region_of[m]][layer_of[m]] += 1

    print("\n=== Plan: mallas por region x capa ===", flush=True)
    hdr = f"{'region':<18} " + " ".join(f"{k[:8]:>9}" for k in LAYER_ORDER) + f" {'total':>7}"
    print(hdr, flush=True)
    print("-" * len(hdr), flush=True)
    for key, _, label, has_skin in REGIONS:
        row = [f"{counts[key].get(k, 0):>9}" for k in LAYER_ORDER]
        tot = sum(counts[key].values())
        print(f"{label:<18} " + " ".join(row) + f" {tot:>7}", flush=True)

    if "--plan" in sys.argv:
        return

    os.makedirs(PUBLIC, exist_ok=True)
    global_lo = np.min([b[0] for b in boxes.values()], axis=0)
    global_hi = np.max([b[1] for b in boxes.values()], axis=0)
    center = (global_lo + global_hi) / 2

    catalog = {
        "layers": [{"key": k, "label": LAYER_LABEL[k]} for k in LAYER_ORDER],
        "regions": [], "overview": None,
        "attribution": "BodyParts3D © The Database Center for Life Science, CC BY-SA 2.1 JP",
    }

    skin_mesh = None
    if any(m for m in assigned if layer_of[m] == "skin" and names.get(m) == "skin"):
        skin_mesh = load_mesh("FMA7163")

    t_start = time.time()
    overview_pool = []
    grand_bytes = grand_tris = 0

    for key, _, label, has_skin in REGIONS:
        mine = [m for m in assigned if region_of[m] == key and layer_of[m] != "skin"]
        if not mine:
            continue
        by_layer = defaultdict(list)
        for m in mine:
            by_layer[layer_of[m]].append(m)

        # piel: recortar la malla de cuerpo entero a la caja de la region
        if has_skin and skin_mesh is not None and key in boxes:
            lo, hi = boxes[key]
            piece = clip_box(skin_mesh.copy(), lo, hi)
            if len(piece.faces) > 0:
                by_layer["skin"] = [("__skin__", piece)]

        # presupuesto proporcional a la complejidad cruda de cada capa
        loaded, raw_tot = {}, 0
        for lk, items in by_layer.items():
            lst = []
            for it in items:
                if isinstance(it, tuple):
                    lst.append((it[0], "skin", it[1]))
                else:
                    lst.append((it, names.get(it, "?"), load_mesh(it)))
            loaded[lk] = lst
            raw_tot += sum(len(x[2].faces) for x in lst)

        region_bytes = region_tris = 0
        region_entry = {"key": key, "label": label, "layers": {}}
        region_lo = np.array([np.inf] * 3)
        region_hi = np.array([-np.inf] * 3)

        for lk in LAYER_ORDER:
            if lk not in loaded:
                continue
            lst = loaded[lk]
            raw = sum(len(x[2].faces) for x in lst)
            budget = max(20_000, int(REGION_BUDGET * raw / max(raw_tot, 1)))
            ratio = min(1.0, budget / max(raw, 1))
            pieces = []
            for fma, nm, mesh in lst:
                d = decimate(mesh, max(MIN_FACES, int(len(mesh.faces) * ratio)))
                pieces.append((fma if fma != "__skin__" else "FMA7163",
                               nm if nm != "skin" else "piel", d))
                if len(d.faces) > MIN_FACES:
                    overview_pool.append((fma, lk, d))
            fname, nbytes, tris, entries, bnd = export_chunk(pieces, f"{key}__{lk}", center)
            region_entry["layers"][lk] = {
                "file": f"/anatomy/{fname}", "bytes": nbytes,
                "tris": tris, "structures": entries,
            }
            if bnd:
                region_lo = np.minimum(region_lo, bnd["min"])
                region_hi = np.maximum(region_hi, bnd["max"])
            region_bytes += nbytes
            region_tris += tris

        # Encuadre: el visor apunta la camara aca, no al origen global.
        region_entry["bounds"] = {
            "min": [round(float(v), 1) for v in region_lo],
            "max": [round(float(v), 1) for v in region_hi],
        }
        catalog["regions"].append(region_entry)
        grand_bytes += region_bytes
        grand_tris += region_tris
        print(f"  {label:<18} {region_tris:>9,} tris  "
              f"{region_bytes / 1024 / 1024:>6.2f} MB  ({time.time() - t_start:.0f}s)",
              flush=True)

    # --- overview: cuerpo entero en LOD bajo -------------------------------
    print("\nGenerando vista de cuerpo entero...", flush=True)
    raw_ov = sum(len(m.faces) for _, _, m in overview_pool)
    ratio = min(1.0, OVERVIEW_BUDGET / max(raw_ov, 1))
    ov_by_layer = defaultdict(list)
    for fma, lk, mesh in overview_pool:
        d = decimate(mesh, max(24, int(len(mesh.faces) * ratio)))
        if len(d.faces) >= 12:
            ov_by_layer[lk].append((fma, names.get(fma, "?"), d))

    catalog["overview"] = {"layers": {}}
    ov_lo = np.array([np.inf] * 3)
    ov_hi = np.array([-np.inf] * 3)
    for lk, pieces in ov_by_layer.items():
        fname, nbytes, tris, entries, bnd = export_chunk(pieces, f"overview__{lk}", center)
        catalog["overview"]["layers"][lk] = {
            "file": f"/anatomy/{fname}", "bytes": nbytes, "tris": tris,
            "structures": entries,
        }
        if bnd:
            ov_lo = np.minimum(ov_lo, bnd["min"])
            ov_hi = np.maximum(ov_hi, bnd["max"])
        grand_bytes += nbytes
        print(f"  overview/{lk:<10} {tris:>8,} tris  {nbytes / 1024 / 1024:>6.2f} MB",
              flush=True)

    catalog["overview"]["bounds"] = {
        "min": [round(float(v), 1) for v in ov_lo],
        "max": [round(float(v), 1) for v in ov_hi],
    }

    with open(os.path.join(PUBLIC, "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, ensure_ascii=False)

    n_struct = sum(len(l["structures"]) for r in catalog["regions"]
                   for l in r["layers"].values())
    print("\n=== Resumen ===", flush=True)
    print(f"  regiones         : {len(catalog['regions'])}", flush=True)
    print(f"  estructuras      : {n_struct}", flush=True)
    print(f"  triangulos       : {grand_tris:,} (detalle) ", flush=True)
    print(f"  total en disco   : {grand_bytes / 1024 / 1024:.1f} MB", flush=True)
    print(f"  tiempo           : {time.time() - t_start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
