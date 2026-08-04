"""
Abre el .blend de Z-Anatomy y reporta que hay adentro.

Objetivo concreto: saber si trae los nervios perifericos y el arbol vascular que
a BodyParts3D le faltan. Se corre con bpy (Blender como modulo de Python).
"""

import os
import sys
from collections import defaultdict

import bpy

BLEND = os.environ["ZANATOMY_BLEND"]

print(f"Blender  : {bpy.app.version_string}")
print(f"Abriendo : {BLEND}  ({os.path.getsize(BLEND) / 1024 / 1024:.0f} MB)", flush=True)

bpy.ops.wm.open_mainfile(filepath=BLEND)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
print(f"\nObjetos totales : {len(bpy.data.objects)}")
print(f"Mallas          : {len(meshes)}")
print(f"Colecciones     : {len(bpy.data.collections)}")


def top_chain(col, depth=0):
    """Devuelve el nombre de la coleccion raiz de una jerarquia."""
    return col.name


# Jerarquia de colecciones de primer y segundo nivel
scene_root = bpy.context.scene.collection
print("\n=== Colecciones de primer nivel ===")


def count_meshes(col):
    n = len([o for o in col.all_objects if o.type == "MESH"])
    return n


for col in scene_root.children:
    print(f"  {col.name:<44} {count_meshes(col):>5} mallas")
    for sub in col.children:
        print(f"     └ {sub.name:<39} {count_meshes(sub):>5}")

# Busqueda por palabra clave: lo que nos falta
print("\n=== Cobertura de lo que a BodyParts3D le falta ===")
KEYS = {
    "nervios perifericos": ["nerve", "nervus", "plexus", "ganglion", "ramus"],
    "  intercostal": ["intercostal nerve"],
    "  frenico": ["phrenic"],
    "  vago": ["vagus"],
    "  plexo braquial": ["brachial plexus"],
    "  ciatico": ["sciatic"],
    "arterias": ["artery", "arteria", "arterial"],
    "venas": ["vein", "vena", "venous"],
    "linfatico": ["lymph"],
}

names = [o.name.lower() for o in meshes]
for label, keys in KEYS.items():
    hits = [n for n in names if any(k in n for k in keys)]
    print(f"  {label:<22} {len(hits):>5} mallas")
    for h in hits[:3]:
        print(f"        p.ej. {h[:62]}")

# Presupuesto de geometria
total_tris = 0
for o in meshes:
    me = o.data
    total_tris += len(me.polygons)
print(f"\nPoligonos totales : {total_tris:,}")
print(f"Promedio por malla: {total_tris // max(len(meshes), 1):,}")
