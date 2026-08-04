"""
Descarga los STL de BodyParts3D listados en el manifiesto, en paralelo.

Reanudable: si el archivo ya existe con el tamano correcto, lo saltea.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

RAW = os.environ["BP3D_RAW"]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
DEST = os.path.join(RAW, "stl")
BASE = "https://raw.githubusercontent.com/Kevin-Mattheus-Moerman/BodyParts3D/main/"

# La piel es una malla de cuerpo entero: no aparece al recortar por region,
# pero la necesitamos igual (se recorta despues geometricamente).
EXTRA = [{
    "fma": "FMA7163",
    "name": "skin",
    "layer": "skin",
    "path": "assets/BodyParts3D_data/stl/FMA7163.stl",
    "size": 79_400_000,
}]

os.makedirs(DEST, exist_ok=True)


def collect():
    with open(os.path.join(OUT, "download_manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    jobs = []
    for layer, data in manifest.items():
        for f in data["files"]:
            jobs.append({**f, "layer": layer})
    jobs.extend(EXTRA)
    return jobs


def fetch(job, session):
    dest = os.path.join(DEST, job["fma"] + ".stl")
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return job, os.path.getsize(dest), True
    r = session.get(BASE + job["path"], timeout=180)
    r.raise_for_status()
    with open(dest, "wb") as fh:
        fh.write(r.content)
    return job, len(r.content), False


def main():
    jobs = collect()
    total_expected = sum(j["size"] for j in jobs)
    print(f"Archivos a bajar : {len(jobs)}")
    print(f"Peso estimado    : {total_expected / 1024 / 1024:.0f} MB")
    print(f"Destino          : {DEST}\n")

    session = requests.Session()
    session.headers["User-Agent"] = "medicin-app-spike"

    done = cached = failed = 0
    got = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(fetch, j, session): j for j in jobs}
        for fut in as_completed(futures):
            job = futures[fut]
            try:
                _, size, was_cached = fut.result()
                got += size
                done += 1
                cached += 1 if was_cached else 0
            except Exception as exc:
                failed += 1
                print(f"  FALLO {job['fma']}: {exc}")
                continue
            if done % 20 == 0 or done == len(jobs):
                pct = got / 1024 / 1024
                print(f"  {done:>3}/{len(jobs)}  {pct:>7.1f} MB  "
                      f"({time.time() - t0:.0f}s)")

    print(f"\nListo: {done} archivos ({cached} ya estaban en cache), {failed} fallos")
    print(f"Total en disco: {got / 1024 / 1024:.1f} MB en {time.time() - t0:.0f}s")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
