"""
Diagnostica por que 'skin' y 'nervous' quedaron vacios al recortar por region.

Hipotesis: la piel es una malla de cuerpo entero (no se descompone por region) y
los nervios no tienen relacion part-of hacia 'thorax' en conventional_part_of.
"""

import csv
import json
import os
from collections import defaultdict, deque

RAW = os.environ["BP3D_RAW"]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")


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


children, names = build()
with open(os.path.join(OUT, "stl_index.json"), encoding="utf-8-sig") as fh:
    stl = {os.path.basename(r["path"])[:-4]: r["size"] for r in json.load(fh)}

print("=== INTEGUMENTARY: que mallas existen ===")
for m in sorted(desc(children, "FMA72979")):
    mark = f"{stl[m] / 1024 / 1024:.1f} MB" if m in stl else "-- sin malla"
    print(f"  {m:<12} {names.get(m, '?'):<42} {mark}")

print("\n=== NERVOUS: estructuras con malla (todas) ===")
nerv = sorted(m for m in desc(children, "FMA7157") if m in stl)
print(f"  total con malla: {len(nerv)}")
for m in nerv:
    print(f"  {m:<12} {names.get(m, '?'):<52} {stl[m] / 1024:>7.0f} KB")

print("\n=== NERVOUS: padres part-of de un nervio de ejemplo ===")
parents = defaultdict(set)
for row in read_tsv(os.path.join(RAW, "conventional_part_of.txt")):
    if len(row) >= 4:
        parents[row[2]].add(row[0])
for probe in nerv[:6]:
    ps = [f"{p} ({names.get(p, '?')})" for p in parents.get(probe, ())]
    print(f"  {probe} {names.get(probe, '?')[:34]:<34} <- {ps or 'SIN PADRE'}")
