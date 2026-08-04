"""
Responde: cuanto del cuerpo se puede cubrir realmente.

Cruza region anatomica x capa x disponibilidad de malla, y reporta que fraccion
de los 934 STL queda asignada a alguna region (el resto necesita asignacion
espacial por bounding box, no ontologica).
"""

import csv
import json
import os
from collections import defaultdict, deque

RAW = os.environ["BP3D_RAW"]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

LAYERS = {
    "skin":     "FMA72979",
    "vascular": "FMA7161",
    "muscular": "FMA72954",
    "skeletal": "FMA23881",
    "nervous":  "FMA7157",
}

# Sistemas viscerales: no son una "capa" pero son contenido central del atlas.
VISCERA = {
    "respiratory": "FMA7158",
    "alimentary":  "FMA7152",
    "urinary":     "FMA7159",
    "genital":     "FMA7160",
    "endocrine":   "FMA9668",
    "lymphoid":    "FMA74594",
    "sense":       "FMA78499",
}


def read_tsv(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        r = csv.reader(fh, delimiter="\t")
        next(r, None)
        for row in r:
            if row:
                yield row


def build():
    children = defaultdict(set)
    names = {}
    for row in read_tsv(os.path.join(RAW, "conventional_part_of.txt")):
        if len(row) >= 4:
            children[row[0]].add(row[2])
    for row in read_tsv(os.path.join(RAW, "composite_parts.txt")):
        if len(row) >= 4:
            children[row[0]].add(row[2])
    for row in read_tsv(os.path.join(RAW, "parts_list_e.txt")):
        if len(row) >= 2:
            names[row[0]] = row[1]
    return children, names


def desc(children, root):
    seen, q = set(), deque([root])
    while q:
        for c in children.get(q.popleft(), ()):
            if c not in seen:
                seen.add(c)
                q.append(c)
    return seen


def main():
    children, names = build()
    with open(os.path.join(OUT, "stl_index.json"), encoding="utf-8-sig") as fh:
        stl = {os.path.basename(r["path"])[:-4]: r["size"] for r in json.load(fh)}

    print(f"Mallas disponibles: {len(stl)}   "
          f"({sum(stl.values()) / 1024 / 1024:.0f} MB crudos)\n")

    # --- Regiones anatomicas (hijos de 'cardinal body part') -----------------
    regions = sorted(children.get("FMA7153", ()),
                     key=lambda f: -len(desc(children, f) & set(stl)))

    print("=== Regiones del cuerpo: mallas disponibles por capa ===")
    hdr = (f"{'region':<26} {'total':>6} " +
           " ".join(f"{k[:6]:>7}" for k in LAYERS))
    print(hdr)
    print("-" * len(hdr))

    layer_sets = {k: desc(children, v) for k, v in LAYERS.items()}
    region_report = {}
    covered = set()

    for reg in regions:
        rset = desc(children, reg) & set(stl)
        if not rset:
            continue
        covered |= rset
        cols = []
        per_layer = {}
        for k, members in layer_sets.items():
            hit = rset & members
            per_layer[k] = sorted(hit)
            cols.append(f"{len(hit):>7}")
        region_report[reg] = {
            "name": names.get(reg, "?"),
            "total": len(rset),
            "bytes": sum(stl[m] for m in rset),
            "layers": per_layer,
        }
        print(f"{names.get(reg, '?')[:26]:<26} {len(rset):>6} " + " ".join(cols))

    # --- Visceras ------------------------------------------------------------
    print("\n=== Sistemas viscerales (contenido, no capa) ===")
    visc_report = {}
    for k, root in VISCERA.items():
        hit = desc(children, root) & set(stl)
        covered |= hit
        visc_report[k] = sorted(hit)
        mb = sum(stl[m] for m in hit) / 1024 / 1024
        print(f"  {k:<14} {len(hit):>4} mallas   {mb:>7.1f} MB")

    # --- Cobertura global ----------------------------------------------------
    orphan = sorted(set(stl) - covered)
    print(f"\n=== Cobertura ===")
    print(f"  asignadas a region o sistema : {len(covered):>4} / {len(stl)} "
          f"({100 * len(covered) / len(stl):.0f}%)")
    print(f"  sin asignar                  : {len(orphan):>4} "
          f"(necesitan asignacion espacial por bounding box)")
    if orphan:
        print("\n  muestra de no asignadas:")
        for o in orphan[:12]:
            print(f"    {o:<12} {names.get(o, '?')[:52]}")

    with open(os.path.join(OUT, "coverage.json"), "w", encoding="utf-8") as fh:
        json.dump({"regions": region_report, "viscera": visc_report,
                   "orphans": orphan}, fh, ensure_ascii=False, indent=1)
    print(f"\nEscrito: {os.path.join(OUT, 'coverage.json')}")


if __name__ == "__main__":
    main()
