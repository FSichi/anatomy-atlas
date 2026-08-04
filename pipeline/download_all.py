"""
Descarga los 934 STL de BodyParts3D (~1,25 GB). Reanudable y en paralelo.
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

RAW = os.environ["BP3D_RAW"]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
DEST = os.path.join(RAW, "stl")
BASE = "https://raw.githubusercontent.com/Kevin-Mattheus-Moerman/BodyParts3D/main/"

os.makedirs(DEST, exist_ok=True)


def fetch(row, session):
    stem = os.path.basename(row["path"])[:-4]
    dest = os.path.join(DEST, stem + ".stl")
    if os.path.exists(dest) and os.path.getsize(dest) == row["size"]:
        return row["size"], True
    r = session.get(BASE + row["path"], timeout=300)
    r.raise_for_status()
    with open(dest, "wb") as fh:
        fh.write(r.content)
    return len(r.content), False


def main():
    with open(os.path.join(OUT, "stl_index.json"), encoding="utf-8-sig") as fh:
        rows = json.load(fh)

    total = sum(r["size"] for r in rows)
    print(f"Archivos : {len(rows)}")
    print(f"Peso     : {total / 1024 / 1024:.0f} MB\n", flush=True)

    session = requests.Session()
    session.headers["User-Agent"] = "medicin-app-fullbody"

    got = done = cached = failed = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(fetch, r, session): r for r in rows}
        for fut in as_completed(futures):
            try:
                size, was_cached = fut.result()
                got += size
                cached += 1 if was_cached else 0
            except Exception as exc:
                failed += 1
                print(f"  FALLO {futures[fut]['path']}: {exc}", flush=True)
            done += 1
            if done % 100 == 0 or done == len(rows):
                print(f"  {done:>4}/{len(rows)}  {got / 1024 / 1024:>7.0f} MB  "
                      f"({time.time() - t0:.0f}s)", flush=True)

    print(f"\nListo: {done} archivos, {cached} en cache, {failed} fallos, "
          f"{got / 1024 / 1024:.0f} MB en {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
