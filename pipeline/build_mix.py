"""
Catalogo combinado: toma de cada fuente la capa donde es mejor.

No genera geometria nueva. Ambas fuentes ya estan en el MISMO espacio (la
transformacion de similitud tiene 0,5 mm de residuo), asi que basta referenciar
los GLB que ya existen y unir sus catalogos.

Reparto, decidido por el censo real de cada fuente:

  de BodyParts3D   vasos (64 mallas contra 22), piel, y organos
  de Z-Anatomy     articulaciones, inserciones, linfoide (no existen en la otra)
  el mejor de dos  huesos, musculos y nervios -> se elige por cantidad

Uso:  python build_mix.py
"""

import json
import os
import shutil
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", "app"))
ANATOMY = os.path.join(APP, "public", "anatomy")

# capa -> fuente elegida y por que
CHOICE = {
    "skin":       ("bodyparts3d", "unica fuente con piel"),
    "vascular":   ("bodyparts3d", "64 mallas contra 22"),
    "organs":     ("bodyparts3d", "mejor cobertura visceral"),
    "skeletal":   ("bodyparts3d", "mejor reparto por region"),
    "nervous":    ("bodyparts3d", "equivalentes; se mantiene la ontologia FMA"),
    "muscular":   ("zanatomy",    "670 contra 437"),
    "joints":     ("zanatomy",    "no existe en BodyParts3D"),
    "insertions": ("zanatomy",    "no existe en BodyParts3D"),
    "lymphoid":   ("zanatomy",    "159 contra ~5"),
}

LAYER_ORDER = ["skeletal", "joints", "insertions", "organs", "lymphoid",
               "vascular", "nervous", "muscular", "skin"]

LAYER_LABEL = {
    "skeletal": "Huesos", "joints": "Articulaciones", "insertions": "Inserciones",
    "organs": "Órganos", "lymphoid": "Linfoide", "vascular": "Vasos",
    "nervous": "Nervios", "muscular": "Músculos", "skin": "Piel",
}


def load(src):
    p = os.path.join(ANATOMY, src, "catalog.json")
    if not os.path.exists(p):
        raise SystemExit(f"falta {p} — generá primero la fuente '{src}'")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def merge_bounds(a, b):
    if not a:
        return b
    if not b:
        return a
    return {
        "min": [min(a["min"][i], b["min"][i]) for i in range(3)],
        "max": [max(a["max"][i], b["max"][i]) for i in range(3)],
    }


def main():
    cats = {s: load(s) for s in ("bodyparts3d", "zanatomy")}
    dest = os.path.join(ANATOMY, "mix")
    os.makedirs(dest, exist_ok=True)

    # Las regiones son las mismas en ambas: se recorren por clave.
    regions = {}
    for src, cat in cats.items():
        for r in cat["regions"]:
            regions.setdefault(r["key"], {"key": r["key"], "label": r["label"],
                                          "layers": {}, "bounds": None})

    out = {
        "layers": [{"key": k, "label": LAYER_LABEL[k]} for k in LAYER_ORDER],
        "regions": [], "overview": {"layers": {}, "bounds": None},
        "attribution": "BodyParts3D © The Database Center for Life Science "
                       "(CC BY-SA 2.1 JP) + Z-Anatomy (CC BY-SA 4.0)",
        "provenance": {k: v[0] for k, v in CHOICE.items()},
    }

    stats = defaultdict(lambda: {"structures": 0, "bytes": 0})

    for key, base in regions.items():
        entry = {"key": key, "label": base["label"], "layers": {}, "bounds": None}
        for layer in LAYER_ORDER:
            src = CHOICE[layer][0]
            src_region = next((r for r in cats[src]["regions"] if r["key"] == key), None)
            chunk = src_region["layers"].get(layer) if src_region else None
            if not chunk:
                continue
            entry["layers"][layer] = chunk
            entry["bounds"] = merge_bounds(entry["bounds"], src_region.get("bounds"))
            stats[layer]["structures"] += len(chunk.get("structures", []))
            stats[layer]["bytes"] += chunk["bytes"]
        if entry["layers"]:
            out["regions"].append(entry)

    for layer in LAYER_ORDER:
        src = CHOICE[layer][0]
        chunk = cats[src]["overview"]["layers"].get(layer)
        if chunk:
            out["overview"]["layers"][layer] = chunk
            out["overview"]["bounds"] = merge_bounds(
                out["overview"]["bounds"], cats[src]["overview"].get("bounds"))

    with open(os.path.join(dest, "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)

    # La nomenclatura se une: las claves no chocan (FMA... contra nombres).
    terms = {}
    for src in ("bodyparts3d", "zanatomy"):
        p = os.path.join(ANATOMY, src, "terms.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                terms.update(json.load(fh))
    with open(os.path.join(dest, "terms.json"), "w", encoding="utf-8") as fh:
        json.dump(terms, fh, ensure_ascii=False)

    print("=== Catalogo combinado ===")
    print(f"{'capa':<12}{'fuente':<14}{'estructuras':>12}{'MB':>8}   motivo")
    print("-" * 78)
    tot_s = tot_b = 0
    for layer in LAYER_ORDER:
        src, why = CHOICE[layer]
        s = stats[layer]
        tot_s += s["structures"]
        tot_b += s["bytes"]
        print(f"{LAYER_LABEL[layer]:<12}{src:<14}{s['structures']:>12}"
              f"{s['bytes'] / 1024 / 1024:>8.2f}   {why}")
    print("-" * 78)
    print(f"{'TOTAL':<26}{tot_s:>12}{tot_b / 1024 / 1024:>8.2f}")
    print(f"\nregiones  : {len(out['regions'])}")
    print(f"terminos  : {len(terms)}")
    print(f"salida    : {dest}")
    print("\nNo se duplica geometria: el combinado referencia los GLB que ya existen.")


if __name__ == "__main__":
    main()
