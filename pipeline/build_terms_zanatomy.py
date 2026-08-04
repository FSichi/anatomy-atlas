"""
Nomenclatura de Z-Anatomy -> Terminologia Anatomica 2.

Ventaja sobre el mapeo de BodyParts3D: el propio TA2.csv viene del repositorio
de Z-Anatomy, asi que sus nombres deberian coincidir casi literalmente.

Convencion de sufijos de Z-Anatomy:
  .l / .r     izquierda / derecha
  .ol / .or   idem, variante "outer"
  .el / .er   idem, variante "extra"
  .i          insercion muscular
  .j          marcador de etiqueta (sin geometria, no llega hasta aca)
  .g          grupo
"""

import json
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", "app"))
PUBLIC = os.path.join(APP, "public", "anatomy", "zanatomy")
TA2 = os.environ["TA2_CSV"]

LANGS = ["English", "Latin", "Français", "Español", "Portugues", "Italiano"]
CODE = {"English": "en", "Latin": "la", "Français": "fr",
        "Español": "es", "Portugues": "pt", "Italiano": "it"}

SIDE_SUFFIX = {
    "l": "left", "r": "right",
    "ol": "left", "or": "right",
    "el": "left", "er": "right",
}


def load_ta2():
    rows = []
    with open(TA2, encoding="utf-8-sig") as fh:
        header = None
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.startswith('"') and line.endswith('"'):
                line = line[1:-1]
            parts = line.split(";")
            if header is None:
                header = parts
                continue
            if len(parts) < len(header):
                parts += [""] * (len(header) - len(parts))
            rows.append(dict(zip(header, parts)))
    return rows


def split_name(name):
    """'Superficial part of masseter.l' -> ('Superficial part of masseter', 'left').

    Los sufijos pueden llevar numero de variante ('.o1r', '.o2l' para origenes
    numerados), asi que se acepta cualquier combinacion de letras y digitos y el
    lado se deduce de la ultima letra.
    """
    m = re.match(r"^(.*?)\.([a-z][a-z0-9]*)(\.\d+)?$", name)
    if not m:
        return name, None
    base, suf = m.group(1), m.group(2)
    if suf in SIDE_SUFFIX:
        return base, SIDE_SUFFIX[suf]
    if suf[-1] == "l":
        return base, "left"
    if suf[-1] == "r":
        return base, "right"
    return base, None


def norm(s):
    s = s.lower().strip()
    s = re.sub(r"[()\[\]]", " ", s)          # Z-Anatomy encierra variantes
    s = re.sub(r"\b(the|of|a|an)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def singular(s):
    out = []
    for t in s.split():
        if len(t) > 4:
            if t.endswith("ae"):
                t = t[:-1]
            elif t.endswith("ies"):
                t = t[:-3] + "y"
            elif t.endswith("s") and not t.endswith("ss"):
                t = t[:-1]
        out.append(t)
    return " ".join(out)


def gender_of(es):
    head = es.strip().split()[0].lower() if es.strip() else ""
    return "f" if head.endswith(("a", "ción", "sión", "is")) else "m"


def main():
    ta2 = load_ta2()
    index, index_s = defaultdict(list), defaultdict(list)
    for r in ta2:
        en = (r.get("English") or "").strip()
        if not en:
            continue
        for v in {en, re.sub(r"\[.*?\]", " ", en).strip()}:
            if v:
                index[norm(v)].append(r)
                index_s[singular(norm(v))].append(r)

    with open(os.path.join(PUBLIC, "catalog.json"), encoding="utf-8") as fh:
        cat = json.load(fh)

    names = {}
    for r in cat["regions"]:
        for layer in r["layers"].values():
            for s in layer.get("structures", []):
                names[s["fma"]] = s["name"]

    print(f"Estructuras en el catalogo : {len(names)}")
    print(f"Claves TA2                 : {len(index)}")

    SUFFIXES = ["muscle", "bone", "nerve", "artery", "vein", "joint", "ligament"]

    def lookup(base):
        for idx, key in ((index, norm(base)), (index_s, singular(norm(base)))):
            hit = idx.get(key)
            if hit:
                return hit[0]
        for suf in SUFFIXES:
            hit = index_s.get(singular(norm(f"{base} {suf}")))
            if hit:
                return hit[0]
        # descartar modificadores por izquierda, conservando 2+ palabras
        toks = singular(norm(base)).split()
        for start in range(1, max(1, len(toks) - 1)):
            hit = index_s.get(" ".join(toks[start:]))
            if hit:
                return hit[0]
        return None

    terms, hits = {}, 0
    for key, raw in names.items():
        base, side = split_name(raw)
        row = lookup(base)
        entry = {"en": base}
        if side:
            entry["side"] = side
        if row:
            hits += 1
            for lang in LANGS:
                v = (row.get(lang) or "").strip()
                if v:
                    entry[CODE[lang]] = v
            entry["ta2"] = row.get("TA2ID", "")
            entry["en"] = base
            if "es" in entry and side:
                g = gender_of(entry["es"])
                entry["es"] += (
                    (" derecha" if g == "f" else " derecho") if side == "right"
                    else (" izquierda" if g == "f" else " izquierdo")
                )
        terms[key] = entry

    con_es = sum(1 for e in terms.values() if "es" in e)
    print(f"\n  con match TA2         : {hits} ({100 * hits / max(len(terms), 1):.0f}%)")
    print(f"  con nombre en espanol : {con_es} ({100 * con_es / max(len(terms), 1):.0f}%)")

    print("\n  ejemplos:")
    shown = 0
    for k, e in terms.items():
        if "es" in e and shown < 10:
            print(f"    {e['en'][:38]:<40} -> {e['es'][:34]:<36} [{e.get('la','')[:22]}]")
            shown += 1

    misses = [e["en"] for e in terms.values() if "es" not in e]
    if misses:
        print(f"\n  sin match ({len(misses)}), muestra:")
        for m in misses[:10]:
            print(f"    {m[:64]}")

    dest = os.path.join(PUBLIC, "terms.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(terms, fh, ensure_ascii=False)
    print(f"\nEscrito: {dest}  ({os.path.getsize(dest) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
