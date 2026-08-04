"""
Une los nombres de BodyParts3D (ingles, via FMA) con Terminologia Anatomica 2,
que trae la nomenclatura oficial en 7 idiomas.

Salida: app/public/anatomy/terms.json  ->  { FMAID: {es, en, la, ...} }
"""

import csv
import json
import os
import re
import sys
from collections import defaultdict

RAW = os.environ["BP3D_RAW"]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
PUBLIC = os.path.abspath(os.path.join(HERE, "..", "app", "public", "anatomy"))
TA2 = os.path.join(RAW, "..", "TA2.csv")

LANGS = ["English", "Latin", "Français", "Español", "Portugues", "Italiano"]
CODE = {"English": "en", "Latin": "la", "Français": "fr",
        "Español": "es", "Portugues": "pt", "Italiano": "it"}

# Lateralidad: TA2 no repite izquierda/derecha, BodyParts3D si.
SIDE = {"right": "right", "left": "left"}

# BodyParts3D numera cada pieza ("novena vertebra toracica"); TA2 usa el termino
# generico. Se separa el ordinal y despues se re-adjunta como numero romano,
# que ademas es la convencion clinica.
ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
    "twelfth": 12,
}
ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def strip_ordinal(s):
    """Devuelve (texto sin ordinal, n) o (texto, None)."""
    for word, n in ORDINALS.items():
        if re.search(rf"\b{word}\b", s, re.I):
            return re.sub(rf"\b{word}\b", " ", s, flags=re.I), n
    return s, None


def singularize(tok):
    if len(tok) > 4:
        if tok.endswith("ae"):
            return tok[:-1]        # vertebrae -> vertebra
        if tok.endswith("ies"):
            return tok[:-3] + "y"  # arteries -> artery
        if tok.endswith("es") and tok[-3] not in "aeiou":
            return tok[:-2]
        if tok.endswith("s") and not tok.endswith("ss"):
            return tok[:-1]
    return tok


def norm(s, singular=False):
    """Clave de comparacion: minusculas, sin puntuacion ni palabras de relleno."""
    s = s.lower().strip()
    s = re.sub(r"\b(right|left)\b", " ", s)
    s = re.sub(r",\s*nsn$", "", s)
    s = re.sub(r"\b(set|segment|part|subdivision)s? of\b", " ", s)
    s = re.sub(r"\b(the|of|a|an)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    toks = s.split()
    if singular:
        toks = [singularize(t) for t in toks]
    return " ".join(toks)


def gender_of(es):
    """Heuristica de genero sobre el nucleo del termino en espanol.

    En anatomia el sustantivo va primero ('Arteria femoral', 'Musculo recto'),
    asi que la terminacion de la primera palabra decide. Muy fiable en este
    vocabulario.
    """
    head = es.strip().split()[0].lower() if es.strip() else ""
    return "f" if head.endswith(("a", "ción", "sión", "is")) else "m"


def load_ta2():
    """El CSV viene con cada linea entre comillas y separado por ';'."""
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


def main():
    ta2 = load_ta2()
    print(f"Filas en TA2        : {len(ta2)}")

    # Dos indices: exacto y singularizado, para resolver plural/singular.
    index, index_sing = defaultdict(list), defaultdict(list)
    for r in ta2:
        en = (r.get("English") or "").strip()
        if not en:
            continue
        # TA2 anota variantes entre corchetes ('Atlas [CI]'); indexamos ambas.
        variants = {en}
        stripped = re.sub(r"\[.*?\]", " ", en).strip()
        if stripped:
            variants.add(stripped)
        for v in variants:
            index[norm(v)].append(r)
            index_sing[norm(v, singular=True)].append(r)
    print(f"Claves inglesas     : {len(index)}")

    # BodyParts3D omite el sustantivo de tipo que TA2 si escribe:
    # 'external oblique' vs 'External oblique muscle'.
    SUFFIXES = ["muscle", "bone", "nerve", "artery", "vein", "gyrus", "cartilage"]

    def lookup(en):
        """Cascada de estrategias, de mas estricta a mas laxa.
        Devuelve (fila TA2, ordinal o None, estrategia)."""
        base, ordinal = strip_ordinal(en)
        for singular in (False, True):
            for text, ordn in ((en, None), (base, ordinal)):
                idx = index_sing if singular else index
                hit = idx.get(norm(text, singular=singular))
                if hit:
                    how = ("sing" if singular else "exact") + ("+ord" if ordn else "")
                    return hit[0], ordn, how
        # Reintento agregando el sustantivo de tipo que BodyParts3D omite.
        for text, ordn in ((en, None), (base, ordinal)):
            for suf in SUFFIXES:
                hit = index_sing.get(norm(f"{text} {suf}", singular=True))
                if hit:
                    return hit[0], ordn, f"+{suf}"
        # Ultimo recurso: descartar modificadores de izquierda a derecha
        # ('humeral head of extensor carpi' -> 'extensor carpi'), conservando
        # al menos dos palabras para no caer en terminos genericos.
        toks = norm(base, singular=True).split()
        for start in range(1, max(1, len(toks) - 1)):
            hit = index_sing.get(" ".join(toks[start:]))
            if hit:
                return hit[0], ordinal, "sufijo"
        return None, ordinal, None

    fma_names = {}
    with open(os.path.join(RAW, "parts_list_e.txt"), encoding="utf-8",
              errors="replace") as fh:
        rd = csv.reader(fh, delimiter="\t")
        next(rd, None)
        for row in rd:
            if len(row) >= 2:
                fma_names[row[0]] = row[1]

    # Solo nos interesan las estructuras que tienen malla.
    with open(os.path.join(OUT, "stl_index.json"), encoding="utf-8-sig") as fh:
        have = {os.path.basename(r["path"])[:-4] for r in json.load(fh)}

    terms, misses = {}, []
    how_count = defaultdict(int)

    for fma in sorted(have):
        en = fma_names.get(fma)
        if not en:
            continue
        side = next((k for k in SIDE if re.search(rf"\b{k}\b", en.lower())), None)
        row, ordinal, how = lookup(en)

        entry = {"en": en}
        if side:
            entry["side"] = SIDE[side]

        if row:
            how_count[how] += 1
            for lang in LANGS:
                v = (row.get(lang) or "").strip()
                if v:
                    entry[CODE[lang]] = v
            entry["ta2"] = row.get("TA2ID", "")
            entry["en"] = en  # conservamos el nombre original, mas especifico

            if "es" in entry:
                es = entry["es"]
                if ordinal:
                    es = f"{es} {ROMAN[ordinal]}"
                if side:
                    g = gender_of(entry["es"])
                    es += (" derecha" if g == "f" else " derecho") if side == "right" \
                        else (" izquierda" if g == "f" else " izquierdo")
                entry["es"] = es
        else:
            misses.append((fma, en))
        terms[fma] = entry

    con_es = sum(1 for e in terms.values() if "es" in e)
    print(f"\nEstructuras con malla  : {len(terms)}")
    print(f"  con nombre en espanol : {con_es} "
          f"({100 * con_es / max(len(terms), 1):.0f}%)")
    print(f"  sin match             : {len(misses)}")
    print("  por estrategia        : " +
          ", ".join(f"{k}={v}" for k, v in sorted(how_count.items())))

    print("\n  ejemplos resueltos:")
    shown = 0
    for fma, e in terms.items():
        if "es" in e and shown < 10:
            print(f"    {e['en'][:40]:<40} -> {e['es'][:38]:<38} [{e.get('la','')[:24]}]")
            shown += 1

    if misses:
        print("\n  sin match (muestra):")
        for fma, en in misses[:10]:
            print(f"    {fma:<11} {en[:56]}")

    os.makedirs(PUBLIC, exist_ok=True)
    dest = os.path.join(PUBLIC, "terms.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(terms, fh, ensure_ascii=False)
    print(f"\nEscrito: {dest}  ({os.path.getsize(dest) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
