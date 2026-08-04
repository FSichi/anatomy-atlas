"""
Cruza las capas FMA con la region anatomica y con los STL realmente disponibles.

Salida: manifiesto de descarga (que archivos bajar, agrupados por capa) y el
presupuesto de bytes crudos antes de procesar.
"""

import csv
import json
import os
import sys
from collections import defaultdict, deque

RAW = os.environ["BP3D_RAW"]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

REGION = ("FMA9576", "thorax")

LAYERS = {
    "skin":     ("FMA72979", "integumentary system"),
    "vascular": ("FMA7161",  "cardiovascular system"),
    "muscular": ("FMA72954", "muscular system"),
    "skeletal": ("FMA23881", "skeletal system"),
    "nervous":  ("FMA7157",  "nervous system"),
}


def read_tsv(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh, delimiter="\t")
        next(reader, None)
        for row in reader:
            if row:
                yield row


def build_graph():
    children = defaultdict(set)
    names = {}
    for row in read_tsv(os.path.join(RAW, "conventional_part_of.txt")):
        if len(row) >= 4:
            children[row[0]].add(row[2])
            names[row[0]] = row[1]
            names[row[2]] = row[3]
    # composite_parts anade relaciones compuesto -> primitiva
    for row in read_tsv(os.path.join(RAW, "composite_parts.txt")):
        if len(row) >= 4:
            children[row[0]].add(row[2])
            names.setdefault(row[0], row[1])
            names.setdefault(row[2], row[3])
    for row in read_tsv(os.path.join(RAW, "parts_list_e.txt")):
        if len(row) >= 2:
            names[row[0]] = row[1]
    return children, names


def descendants(children, root, include_self=True):
    seen = {root} if include_self else set()
    queue = deque([root])
    while queue:
        node = queue.popleft()
        for child in children.get(node, ()):
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return seen


def load_stl_index():
    with open(os.path.join(OUT, "stl_index.json"), encoding="utf-8-sig") as fh:
        rows = json.load(fh)
    idx = {}
    for r in rows:
        stem = os.path.basename(r["path"])[:-4]  # sin .stl
        idx[stem] = {"path": r["path"], "size": r["size"]}
    return idx


def main():
    children, names = build_graph()
    stl = load_stl_index()

    fma_named = sum(1 for k in stl if k.startswith("FMA"))
    print(f"STL totales: {len(stl)}  (FMA*: {fma_named}, BP*: {len(stl) - fma_named})")

    region = descendants(children, REGION[0])
    print(f"Region '{REGION[1]}' ({REGION[0]}): {len(region)} estructuras en el arbol\n")

    manifest = {}
    grand_files = grand_bytes = 0

    header = f"{'capa':<10} {'en capa':>8} {'con STL':>8} {'en region':>10} {'MB crudos':>10}"
    print("=== Capas: cobertura de malla y recorte por region ===")
    print(header)
    print("-" * len(header))

    for key, (root, label) in LAYERS.items():
        members = descendants(children, root, include_self=False)
        with_mesh = {m for m in members if m in stl}
        in_region = sorted(with_mesh & region)

        files = [{"fma": m, "name": names.get(m, "?"), **stl[m]} for m in in_region]
        total = sum(f["size"] for f in files)
        grand_files += len(files)
        grand_bytes += total

        manifest[key] = {"root": root, "label": label, "files": files}
        print(f"{key:<10} {len(members):>8} {len(with_mesh):>8} {len(in_region):>10} "
              f"{total / 1024 / 1024:>9.1f}")

    print("-" * len(header))
    print(f"{'TOTAL':<10} {'':>8} {'':>8} {grand_files:>10} {grand_bytes / 1024 / 1024:>9.1f}")

    dest = os.path.join(OUT, "download_manifest.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print(f"\nManifiesto: {dest}")

    print("\n=== Muestra por capa (5 primeras) ===")
    for key, data in manifest.items():
        print(f"\n[{key}]")
        for f in data["files"][:5]:
            print(f"  {f['fma']:<10} {f['name'][:48]:<48} {f['size'] / 1024:>7.0f} KB")
        if not data["files"]:
            print("  (vacio)")


if __name__ == "__main__":
    main()
