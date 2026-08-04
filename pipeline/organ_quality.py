"""
Cuanto detalle estamos descartando en los organos.

El pipeline decima al ~18% para que un cuerpo entero entre en presupuesto. Pero
al mirar UN organo solo, ese presupuesto no aplica: se puede servir la malla
casi completa. Este script mide la diferencia real.
"""

import json
import os

import trimesh

RAW = os.environ["BP3D_RAW"]
STL = os.path.join(RAW, "stl")
HERE = os.path.dirname(os.path.abspath(__file__))
trimesh.util.log.setLevel("ERROR")

# Organos que un atlas quiere mostrar solos, con sus estructuras acompanantes:
# lo que el sitio de referencia dibuja en la textura, nosotros lo tenemos como
# geometria real y separable.
ORGANS = {
    "Corazón": {
        "core": ["FMA7088"],
        "extra": ["FMA3736", "FMA3768", "FMA3802", "FMA3818", "FMA3840nsn"],
    },
    "Encéfalo": {"core": ["FMA50801"], "extra": ["FMA67944", "FMA62004"]},
    "Hígado": {"core": ["FMA7197"], "extra": []},
    "Riñón der.": {"core": ["FMA7204"], "extra": []},
    "Pulmón der.": {"core": ["FMA7309"], "extra": []},
    "Páncreas": {"core": ["FMA7198"], "extra": []},
    "Estómago": {"core": ["FMA7148"], "extra": []},
    "Bazo": {"core": ["FMA7196"], "extra": []},
}


def load(fma):
    p = os.path.join(STL, fma + ".stl")
    if not os.path.exists(p):
        return None
    m = trimesh.load(p, process=False, force="mesh")
    m.merge_vertices()
    return m


print(f"{'organo':<14}{'piezas':>7}{'tris crudos':>13}{'lo que servimos':>17}{'ratio':>8}")
print("-" * 60)

# Lo que servimos hoy: leer del catalogo generado
cat_path = os.path.join(HERE, "..", "app", "public", "anatomy", "bodyparts3d", "catalog.json")
shipped = {}
if os.path.exists(cat_path):
    with open(cat_path, encoding="utf-8") as fh:
        cat = json.load(fh)
    for r in cat["regions"]:
        for layer in r["layers"].values():
            for s in layer.get("structures", []):
                shipped[s["fma"]] = s["faces"]

total_raw = total_ship = 0
for name, spec in ORGANS.items():
    ids = spec["core"] + spec["extra"]
    raw = ship = 0
    piezas = 0
    for fma in ids:
        m = load(fma)
        if m is None:
            continue
        piezas += 1
        raw += len(m.faces)
        ship += shipped.get(fma, 0)
    if not piezas:
        print(f"{name:<14}{'—':>7}  (sin malla: revisar los FMA)")
        continue
    total_raw += raw
    total_ship += ship
    ratio = f"{100 * ship / raw:.0f}%" if raw else "—"
    print(f"{name:<14}{piezas:>7}{raw:>13,}{ship:>17,}{ratio:>8}")

print("-" * 60)
print(f"{'TOTAL':<14}{'':>7}{total_raw:>13,}{total_ship:>17,}"
      f"{100 * total_ship / max(total_raw,1):>7.0f}%")

print("\nReferencia: el heart.glb del sitio que motivó esto tiene 586.144 "
      "vértices\ny pesa 3,2 MB — una sola malla, sin partes.")
