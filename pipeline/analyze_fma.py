"""
Analiza la jerarquia FMA de BodyParts3D y mapea las capas anatomicas.

Lee conventional_part_of.txt (relaciones part-of) y parts_list_e.txt (nombres),
calcula el cierre transitivo de cada sistema raiz y cruza con los STL disponibles.
"""

import csv
import json
import os
import sys
from collections import defaultdict, deque

RAW = os.environ.get("BP3D_RAW")
if not RAW:
    sys.exit("Falta la variable de entorno BP3D_RAW")

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

# Las 5 capas que queremos, mapeadas a su sistema raiz en FMA.
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
        next(reader, None)  # header
        for row in reader:
            if row:
                yield row


def load_names():
    names = {}
    for row in read_tsv(os.path.join(RAW, "parts_list_e.txt")):
        if len(row) >= 2:
            names[row[0]] = row[1]
    return names


def load_partof():
    """parent_id -> set(child_id). Columnas: id, name, part id, part name."""
    children = defaultdict(set)
    parents = defaultdict(set)
    for row in read_tsv(os.path.join(RAW, "conventional_part_of.txt")):
        if len(row) >= 4:
            parent, child = row[0], row[2]
            children[parent].add(child)
            parents[child].add(parent)
    return children, parents


def descendants(children, root):
    """Cierre transitivo, protegido contra ciclos."""
    seen = set()
    queue = deque([root])
    while queue:
        node = queue.popleft()
        for child in children.get(node, ()):
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return seen


def main():
    names = load_names()
    children, parents = load_partof()

    roots = sorted(children.get("FMA20394", ()))
    print(f"Nombres cargados        : {len(names)}")
    print(f"Nodos con hijos         : {len(children)}")
    print(f"Sistemas raiz del cuerpo: {len(roots)}\n")

    print("=== Sistemas raiz (hijos directos de 'human body') ===")
    for fma in roots:
        n = len(descendants(children, fma))
        print(f"  {fma:<10} {names.get(fma, '?'):<40} {n:>5} descendientes")

    print("\n=== Capas objetivo ===")
    layer_members = {}
    for key, (fma, label) in LAYERS.items():
        desc = descendants(children, fma)
        layer_members[key] = desc
        status = "OK" if desc else "VACIO / revisar ID"
        print(f"  {key:<10} {fma:<10} {label:<24} {len(desc):>5} estructuras  [{status}]")

    # Solapamiento entre capas: una estructura puede pertenecer a mas de un sistema.
    print("\n=== Solapamiento entre capas ===")
    keys = list(LAYERS)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            common = layer_members[a] & layer_members[b]
            if common:
                print(f"  {a} ∩ {b}: {len(common)}")

    payload = {
        "layers": {
            k: {
                "root": LAYERS[k][0],
                "label": LAYERS[k][1],
                "count": len(v),
                "members": sorted(v),
            }
            for k, v in layer_members.items()
        },
        "names": names,
    }
    dest = os.path.join(OUT, "fma_layers.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    print(f"\nEscrito: {dest}")


if __name__ == "__main__":
    main()
