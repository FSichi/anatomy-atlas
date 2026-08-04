"""
Pipeline STL -> GLB por capa anatomica.

  1. carga los STL crudos y reporta geometria
  2. deriva la caja de la region a partir del esqueleto
  3. recorta la piel (malla de cuerpo entero) a esa caja
  4. decima cada malla con un presupuesto de triangulos por capa
  5. exporta un GLB por capa, un nodo nombrado por estructura (FMA ID)

Uso:  python build_assets.py [--stats]
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
import fast_simplification

RAW = os.environ["BP3D_RAW"]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
STL = os.path.join(RAW, "stl")
PUBLIC = os.path.abspath(os.path.join(HERE, "..", "app", "public", "anatomy"))

# Presupuesto de triangulos por capa para la escena web (desktop ~1.2M total).
BUDGET = {
    "skeletal": 320_000,
    "muscular": 380_000,
    "vascular": 180_000,
    "skin":     120_000,
}

LAYER_COLOR = {
    "skin":     [0.92, 0.76, 0.66, 1.0],
    "muscular": [0.70, 0.25, 0.23, 1.0],
    "vascular": [0.69, 0.15, 0.18, 1.0],
    "skeletal": [0.91, 0.89, 0.82, 1.0],
}

trimesh.util.log.setLevel("ERROR")

APP = os.path.abspath(os.path.join(HERE, "..", "app"))
GLTF_CLI = os.path.join(APP, "node_modules", ".bin",
                        "gltf-transform.cmd" if os.name == "nt" else "gltf-transform")


def compress(src, dst):
    """Draco via gltf-transform. Devuelve True si comprimio."""
    if not os.path.exists(GLTF_CLI):
        print("  aviso: falta @gltf-transform/cli, se deja el GLB sin comprimir")
        shutil.copyfile(src, dst)
        return False
    subprocess.run(
        [GLTF_CLI, "draco", src, dst, "--quantize-position", "14"],
        check=True, capture_output=True, shell=(os.name == "nt"),
    )
    return True


def content_name(layer, path):
    """Nombre con hash de contenido: requisito para servir con
    Cache-Control immutable sin quedar servindo una version vieja."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return f"{layer}.{h.hexdigest()[:10]}.glb"


def load_manifest():
    with open(os.path.join(OUT, "download_manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    layers = {}
    for layer, data in manifest.items():
        files = [f for f in data["files"]]
        if files:
            layers[layer] = files
    layers["skin"] = [{"fma": "FMA7163", "name": "skin"}]
    return layers


def load_mesh(fma, weld=True):
    """Los STL son triangle soup (vertices = 3 x caras, sin aristas compartidas).
    Hay que soldar los vertices o la decimacion por colapso de aristas no puede
    hacer nada: sin conectividad no hay aristas que colapsar."""
    path = os.path.join(STL, fma + ".stl")
    m = trimesh.load(path, process=False, force="mesh")
    if weld:
        m.merge_vertices()
    return m


def stats(layers):
    print(f"{'capa':<10} {'piezas':>7} {'triangulos':>13} {'vertices':>12}")
    print("-" * 46)
    grand_t = grand_v = 0
    bounds = []
    for layer, files in layers.items():
        t = v = 0
        for f in files:
            m = load_mesh(f["fma"])
            t += len(m.faces)
            v += len(m.vertices)
            if layer == "skeletal":
                bounds.append(m.bounds)
        grand_t += t
        grand_v += v
        print(f"{layer:<10} {len(files):>7} {t:>13,} {v:>12,}")
    print("-" * 46)
    print(f"{'TOTAL':<10} {'':>7} {grand_t:>13,} {grand_v:>12,}")

    b = np.array(bounds)
    lo, hi = b[:, 0, :].min(axis=0), b[:, 1, :].max(axis=0)
    print(f"\nCaja del esqueleto toracico (mm):")
    print(f"  X {lo[0]:8.1f} .. {hi[0]:8.1f}   ancho  {hi[0]-lo[0]:7.1f}")
    print(f"  Y {lo[1]:8.1f} .. {hi[1]:8.1f}   fondo  {hi[1]-lo[1]:7.1f}")
    print(f"  Z {lo[2]:8.1f} .. {hi[2]:8.1f}   alto   {hi[2]-lo[2]:7.1f}")
    return lo, hi, grand_t


def region_box(layers):
    bounds = [load_mesh(f["fma"]).bounds for f in layers["skeletal"]]
    b = np.array(bounds)
    return b[:, 0, :].min(axis=0), b[:, 1, :].max(axis=0)


def clip_to_box(mesh, lo, hi, pad=12.0):
    """Recorta con planos alineados a los ejes (la piel es cuerpo entero)."""
    planes = [
        ([0, 0, 1], [0, 0, lo[2] - pad]),
        ([0, 0, -1], [0, 0, hi[2] + pad]),
    ]
    for normal, origin in planes:
        if len(mesh.faces) == 0:
            break
        mesh = mesh.slice_plane(plane_origin=origin, plane_normal=normal, cap=False)
    return mesh


def decimate(mesh, target_faces):
    n = len(mesh.faces)
    if n <= target_faces or target_faces < 4:
        return mesh
    verts = np.ascontiguousarray(mesh.vertices, dtype=np.float32)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.uint32)
    v2, f2 = fast_simplification.simplify(verts, faces, 1.0 - target_faces / n)
    return trimesh.Trimesh(vertices=v2, faces=f2, process=False)


def main():
    layers = load_manifest()

    print("=== Geometria cruda ===")
    lo, hi, raw_total = stats(layers)

    if "--stats" in sys.argv:
        return

    os.makedirs(PUBLIC, exist_ok=True)
    print("\n=== Procesando ===")

    # Centro de la region, para dejar el modelo centrado en el origen.
    center = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2])

    catalog = {}
    report = []

    for layer, files in layers.items():
        t0 = time.time()
        loaded = []
        for f in files:
            m = load_mesh(f["fma"])
            if layer == "skin":
                m = clip_to_box(m, lo, hi)
            if len(m.faces) == 0:
                continue
            loaded.append((f, m))

        raw_faces = sum(len(m.faces) for _, m in loaded)
        budget = BUDGET[layer]
        ratio = min(1.0, budget / max(raw_faces, 1))

        scene = trimesh.Scene()
        entries = []
        kept = 0
        for f, m in loaded:
            target = max(64, int(len(m.faces) * ratio))
            d = decimate(m, target)
            d.apply_translation(-center)
            # Color por material, no por cara: los colores por cara obligan a
            # duplicar vertices y disparan el peso del GLB.
            d.visual = trimesh.visual.TextureVisuals(
                material=trimesh.visual.material.PBRMaterial(
                    name=layer,
                    baseColorFactor=LAYER_COLOR[layer],
                    metallicFactor=0.0,
                    roughnessFactor=0.62,
                )
            )
            scene.add_geometry(d, node_name=f["fma"], geom_name=f["fma"])
            kept += len(d.faces)
            entries.append({"fma": f["fma"], "name": f["name"], "faces": len(d.faces)})

        # include_normals: sin NORMAL en el glTF, un material PBR se sombrea
        # plano/negro en three.js.
        tmp_dir = tempfile.mkdtemp()
        plain = os.path.join(tmp_dir, f"{layer}.glb")
        packed = os.path.join(tmp_dir, f"{layer}.draco.glb")
        scene.export(plain, include_normals=True)
        raw_size = os.path.getsize(plain)
        compress(plain, packed)

        # Limpiamos versiones anteriores de esta capa antes de escribir la nueva.
        for old in glob.glob(os.path.join(PUBLIC, f"{layer}.*.glb")):
            os.remove(old)
        fname = content_name(layer, packed)
        dest = os.path.join(PUBLIC, fname)
        shutil.move(packed, dest)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        size = os.path.getsize(dest)

        catalog[layer] = {"file": f"/anatomy/{fname}", "structures": entries}
        report.append((layer, len(entries), raw_faces, kept, size, time.time() - t0))
        print(f"  {layer:<10} {len(entries):>3} piezas  "
              f"{raw_faces:>9,} -> {kept:>8,} tris  "
              f"{raw_size / 1024 / 1024:>6.1f} -> {size / 1024 / 1024:>5.2f} MB  "
              f"({time.time() - t0:.0f}s)")

    with open(os.path.join(PUBLIC, "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, ensure_ascii=False, indent=1)

    tot_raw = sum(r[2] for r in report)
    tot_kept = sum(r[3] for r in report)
    tot_size = sum(r[4] for r in report)
    print("\n=== Resumen ===")
    print(f"  triangulos     : {tot_raw:,} -> {tot_kept:,} "
          f"({100 * tot_kept / tot_raw:.1f}% conservado)")
    print(f"  STL crudo      : 307.3 MB")
    print(f"  GLB + Draco    : {tot_size / 1024 / 1024:.2f} MB  "
          f"({307.3 / (tot_size / 1024 / 1024):.0f}x mas chico)")
    print(f"  salida         : {PUBLIC}")


if __name__ == "__main__":
    main()
