"""
Galeria de organos: un GLB por organo, a la mayor calidad posible.

Por que existe aparte del atlas por capas:
  - el atlas decima al ~22% para que un cuerpo entero entre en presupuesto;
    mirando UN organo solo ese presupuesto no aplica y se sirve la malla completa
  - las visceras de BodyParts3D son de baja densidad (un higado son 19.416
    triangulos), asi que el detalle no se puede inventar — pero SI se puede
    hacer que se lean mucho mejor: subdivision + suavizado de Taubin para matar
    el facetado, y oclusion ambiental horneada en los colores de vertice
  - cada organo agrupa sus piezas reales: el corazon viene con sus coronarias
    como geometria separable, no pintadas en una textura

Uso:  python build_organs.py [--plan]
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

import numpy as np
import trimesh

RAW = os.environ["BP3D_RAW"]
STL = os.path.join(RAW, "stl")
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", "app"))
PUBLIC = os.path.join(APP, "public", "anatomy", "organs")
URL_BASE = "/anatomy/organs"
GLTF_CLI = os.path.join(APP, "node_modules", ".bin",
                        "gltf-transform.cmd" if os.name == "nt" else "gltf-transform")

trimesh.util.log.setLevel("ERROR")

# Debajo de esto la malla se ve facetada y conviene subdividir.
SUBDIVIDE_BELOW = 60_000
# Techo por organo: incluso solo, no tiene sentido pasarse.
MAX_FACES = 220_000

# Tejido: base y acento. El acento distingue las piezas acompanantes
# (coronarias sobre el miocardio, vesicula sobre el higado).
TISSUE = {
    "muscle": [0.72, 0.29, 0.27],
    "vessel": [0.68, 0.16, 0.19],
    "vein": [0.36, 0.36, 0.55],
    "neural": [0.80, 0.74, 0.68],
    "gut": [0.80, 0.56, 0.45],
    "gland": [0.66, 0.42, 0.38],
    "airway": [0.74, 0.72, 0.70],
    "bile": [0.62, 0.63, 0.36],
    "urinary": [0.70, 0.40, 0.34],
    "sense": [0.85, 0.84, 0.82],
}

# Cada entrada de la galeria agrupa las piezas que forman el organo.
ORGANS = [
    {
        "key": "heart", "es": "Corazón", "en": "Heart", "system": "Cardiovascular",
        "parts": [
            ("FMA7088", "muscle"), ("FMA7274", "muscle"),
            ("FMA3736", "vessel"), ("FMA3768", "vessel"), ("FMA3784", "vessel"),
            ("FMA3802", "vessel"), ("FMA3818", "vessel"), ("FMA3840nsn", "vessel"),
            ("FMA4720", "vein"), ("FMA10951", "vein"),
        ],
    },
    {
        "key": "brain", "es": "Encéfalo", "en": "Brain", "system": "Nervioso",
        "parts": [("FMA50801", "neural"), ("FMA67944", "neural"),
                  ("FMA67943", "neural"), ("FMA62004", "neural")],
    },
    {
        "key": "lungs", "es": "Pulmones", "en": "Lungs", "system": "Respiratorio",
        "parts": [("FMA7333", "airway"), ("FMA7337", "airway"), ("FMA7383", "airway"),
                  ("FMA7370", "airway"), ("FMA7371", "airway"),
                  ("FMA7394", "airway"), ("FMA7409", "airway")],
    },
    {
        "key": "liver", "es": "Hígado", "en": "Liver", "system": "Digestivo",
        "parts": [("FMA7197", "gland"), ("FMA7202", "bile")],
    },
    {
        "key": "kidneys", "es": "Riñones", "en": "Kidneys", "system": "Urinario",
        "parts": [("FMA7204", "urinary"), ("FMA7205", "urinary"),
                  ("FMA15629", "gland"), ("FMA15630", "gland"),
                  ("FMA15900", "urinary")],
    },
    {
        "key": "stomach", "es": "Estómago", "en": "Stomach", "system": "Digestivo",
        "parts": [("FMA7148", "gut"), ("FMA7131", "gut"), ("FMA7206", "gut")],
    },
    {
        "key": "intestine", "es": "Intestino", "en": "Intestine", "system": "Digestivo",
        "parts": [("FMA14543nsn", "gut"), ("FMA7207", "gut"), ("FMA7208", "gut")],
    },
    {
        "key": "pancreas", "es": "Páncreas", "en": "Pancreas", "system": "Endocrino",
        "parts": [("FMA7198nsn", "gland")],
    },
    {
        "key": "spleen", "es": "Bazo", "en": "Spleen", "system": "Linfoide",
        "parts": [("FMA7196", "gland")],
    },
    {
        "key": "eye", "es": "Ojo", "en": "Eye", "system": "Sensorial",
        "parts": [("FMA12513", "sense")],
    },
]


def load(fma):
    p = os.path.join(STL, fma + ".stl")
    if not os.path.exists(p):
        return None
    m = trimesh.load(p, process=False, force="mesh")
    m.merge_vertices()  # los STL son triangle soup
    return m


def cavity_ao(mesh, near=0.85, far=1.15, smooth_iters=10):
    """
    Oclusion ambiental aproximada por curvatura, sin trazar rayos.

    Para cada vertice se promedia hacia donde estan sus vecinos. Si ese promedio
    apunta EN EL SENTIDO de la normal, el vertice esta metido en una concavidad
    y debe oscurecerse. Suavizando ese campo sobre el grafo se obtiene una
    escala mas amplia, que es la que da la sensacion de volumen.

    Se hace asi porque no hay embree disponible y trazar rayos con el respaldo
    de numpy sobre 20.000 caras seria de otro orden de magnitud en tiempo.
    """
    v = mesh.vertices
    n = mesh.vertex_normals
    e = mesh.edges_unique
    if not len(e):
        return np.ones(len(v))

    acc = np.zeros_like(v)
    cnt = np.zeros(len(v))
    for a, b in ((e[:, 0], e[:, 1]), (e[:, 1], e[:, 0])):
        np.add.at(acc, a, v[b] - v[a])
        np.add.at(cnt, a, 1.0)
    cnt = np.maximum(cnt, 1.0)[:, None]
    d = acc / cnt

    norm = np.linalg.norm(d, axis=1, keepdims=True) + 1e-9
    curv = np.sum((d / norm) * n, axis=1)          # >0 concavo, <0 convexo

    # Suavizado sobre el grafo: la version amplia de la misma senal.
    wide = curv.copy()
    for _ in range(smooth_iters):
        s = np.zeros(len(v))
        c = np.zeros(len(v))
        for a, b in ((e[:, 0], e[:, 1]), (e[:, 1], e[:, 0])):
            np.add.at(s, a, wide[b])
            np.add.at(c, a, 1.0)
        wide = 0.5 * wide + 0.5 * (s / np.maximum(c, 1.0))

    ao = 1.0 - np.clip(near * np.clip(curv, 0, None) + far * np.clip(wide, 0, None), 0, 0.72)
    return np.clip(ao, 0.28, 1.0)


def refine(mesh):
    """Subdivide y suaviza las mallas facetadas.

    Taubin en vez de Laplaciano: el Laplaciano encoge el volumen en cada
    iteracion y un organo termina mas chico de lo que es.
    """
    if len(mesh.faces) < SUBDIVIDE_BELOW:
        mesh = mesh.subdivide()
    if len(mesh.faces) > MAX_FACES:
        return mesh
    try:
        trimesh.smoothing.filter_taubin(mesh, lamb=0.5, nu=-0.53, iterations=12)
    except Exception:
        pass
    return mesh


def compress(src, dst):
    if not os.path.exists(GLTF_CLI):
        raise SystemExit(f"falta @gltf-transform/cli en {GLTF_CLI}")
    subprocess.run([GLTF_CLI, "draco", src, dst, "--quantize-position", "14",
                    "--quantize-color", "10"],
                   check=True, capture_output=True, shell=(os.name == "nt"))


def content_name(stem, path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return f"{stem}.{h.hexdigest()[:10]}.glb"


def main():
    plan_only = "--plan" in sys.argv
    if not plan_only:
        os.makedirs(PUBLIC, exist_ok=True)

    with open(os.path.join(APP, "public", "anatomy", "bodyparts3d", "terms.json"),
              encoding="utf-8") as fh:
        terms = json.load(fh)

    catalog = {"organs": [], "attribution":
               "BodyParts3D © The Database Center for Life Science · CC BY-SA 2.1 JP"}
    t0 = time.time()
    total_bytes = total_tris = 0

    print(f"{'organo':<12}{'piezas':>7}{'crudo':>10}{'final':>10}{'MB':>7}  detalle")
    print("-" * 62)

    for spec in ORGANS:
        pieces, faltan = [], []
        raw_total = 0
        for fma, tissue in spec["parts"]:
            m = load(fma)
            if m is None:
                faltan.append(fma)
                continue
            raw_total += len(m.faces)
            pieces.append((fma, tissue, m))

        if not pieces:
            print(f"{spec['es']:<12}  sin mallas: {faltan}")
            continue

        if plan_only:
            print(f"{spec['es']:<12}{len(pieces):>7}{raw_total:>10,}"
                  f"{'—':>10}{'—':>7}  faltan={len(faltan)}")
            continue

        # 1. Refinar y calcular oclusion una sola vez por pieza.
        listo, entries, tris = [], [], 0
        lo = np.array([np.inf] * 3)
        hi = np.array([-np.inf] * 3)

        for fma, tissue, m0 in pieces:
            m = refine(m0)
            ao = cavity_ao(m)
            base = np.array(TISSUE[tissue])
            # La oclusion va en el color de vertice; el material la multiplica.
            rgba = np.hstack([np.clip(base[None, :] * ao[:, None], 0, 1),
                              np.ones((len(ao), 1))])
            lo = np.minimum(lo, m.bounds[0])
            hi = np.maximum(hi, m.bounds[1])
            listo.append((fma, m, rgba))
            tris += len(m.faces)
            entries.append({
                "fma": fma, "tissue": tissue, "faces": len(m.faces),
                "name": terms.get(fma, {}).get("en", fma),
            })

        # 2. Centrar: cada organo se mira solo, su origen es su propio centro.
        center = (lo + hi) / 2
        scene = trimesh.Scene()
        for fma, m, rgba in listo:
            m = m.copy()
            m.apply_translation(-center)
            m.visual = trimesh.visual.ColorVisuals(mesh=m, vertex_colors=rgba)
            scene.add_geometry(m, node_name=fma, geom_name=fma)

        tmp = tempfile.mkdtemp()
        plain, packed = os.path.join(tmp, "a.glb"), os.path.join(tmp, "b.glb")
        scene.export(plain, include_normals=True)
        compress(plain, packed)
        for old in glob.glob(os.path.join(PUBLIC, f"{spec['key']}.*.glb")):
            os.remove(old)
        fname = content_name(spec["key"], packed)
        shutil.move(packed, os.path.join(PUBLIC, fname))
        shutil.rmtree(tmp, ignore_errors=True)
        nbytes = os.path.getsize(os.path.join(PUBLIC, fname))

        size = hi - lo
        catalog["organs"].append({
            "key": spec["key"], "es": spec["es"], "en": spec["en"],
            "system": spec["system"], "file": f"{URL_BASE}/{fname}",
            "bytes": nbytes, "tris": tris, "structures": entries,
            "radius": round(float(np.linalg.norm(size) / 2), 1),
            "missing": faltan,
        })
        total_bytes += nbytes
        total_tris += tris
        print(f"{spec['es']:<12}{len(pieces):>7}{raw_total:>10,}{tris:>10,}"
              f"{nbytes / 1024 / 1024:>7.2f}  x{tris / max(raw_total,1):.1f}")

    if plan_only:
        return

    with open(os.path.join(PUBLIC, "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, ensure_ascii=False)

    print("-" * 62)
    print(f"{'TOTAL':<12}{'':>7}{'':>10}{total_tris:>10,}{total_bytes / 1024 / 1024:>7.2f}")
    print(f"\norganos : {len(catalog['organs'])}")
    print(f"tiempo  : {time.time() - t0:.0f}s")
    print(f"salida  : {PUBLIC}")


if __name__ == "__main__":
    main()
