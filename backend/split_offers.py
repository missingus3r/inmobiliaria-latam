#!/usr/bin/env python3
"""split_offers.py — publica data/offers.json partido por país.

data/offers.json es la base maestra local (scrapers + validator la escriben) y ya
no se commitea: pasó los 50 MB y la página la bajaba entera en cada visita
(pedido de Bruno del 2026-10-16, msgs 9433/9434). Este script genera lo que sí
se publica:

  data/offers/<CC>.json           activas del país, con una sola imagen
  data/offers/<CC>-vencidas.json  vencidas del país, sin imágenes
  data/offers/index.json          conteos por país y fecha de generación

Además saca las imágenes de las vencidas en la base maestra: no se muestran y
no hace falta guardarlas. Escritura atómica; sale con exit 1 si la base está
vacía o no se puede leer, para no publicar un país vacío por error.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MASTER = REPO / "data" / "offers.json"
OUT = REPO / "data" / "offers"
DROP_ALWAYS = ("image_url",)  # el front solo usa images[0]


def write_atomic(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def main():
    try:
        offers = json.loads(MASTER.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"no pude leer {MASTER}: {e}", file=sys.stderr)
        return 1
    if not offers:
        print("la base maestra está vacía: no publico nada", file=sys.stderr)
        return 1

    stripped = 0
    for o in offers:
        if o.get("estado") == "vencida" and (o.get("images") or o.get("image_url")):
            o.pop("images", None)
            o.pop("image_url", None)
            stripped += 1
    if stripped:
        write_atomic(MASTER, offers)

    by = defaultdict(lambda: {"activas": [], "vencidas": []})
    for o in offers:
        row = {k: v for k, v in o.items() if k not in DROP_ALWAYS}
        cc = o.get("country") or "XX"
        if o.get("estado") == "vencida":
            by[cc]["vencidas"].append(row)
        else:
            imgs = row.get("images") or []
            if imgs:
                row["images"] = imgs[:1]
            by[cc]["activas"].append(row)

    OUT.mkdir(parents=True, exist_ok=True)
    index = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "countries": {}}
    for cc, parts in sorted(by.items()):
        write_atomic(OUT / f"{cc}.json", parts["activas"])
        write_atomic(OUT / f"{cc}-vencidas.json", parts["vencidas"])
        index["countries"][cc] = {"activas": len(parts["activas"]), "vencidas": len(parts["vencidas"])}
    write_atomic(OUT / "index.json", index)

    total = sum(len(p["activas"]) + len(p["vencidas"]) for p in by.values())
    print(f"split ok · {total} avisos · {len(by)} países · imágenes quitadas a {stripped} vencidas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
