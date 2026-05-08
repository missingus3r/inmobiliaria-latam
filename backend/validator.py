#!/usr/bin/env python3
"""validator.py — verifica que los links de offers.json sigan vivos.

Para cada offer:
  - HEAD request al link (timeout 8s)
  - 2xx/3xx → estado="activa"
  - 4xx/5xx o timeout → estado="vencida"

Concurrencia: 16 hilos. Persiste offers.json atómico.

Uso:
    python3 backend/validator.py [--max-workers 16]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
OFFERS_PATH = REPO / "data" / "offers.json"

HEADERS = {"User-Agent": "LatamHouse-validator/0.2"}


def check(offer: dict) -> tuple[str, str]:
    """Return (id, new_estado)."""
    try:
        r = requests.head(offer["link"], headers=HEADERS, timeout=8, allow_redirects=True)
        if r.status_code < 400:
            return offer["id"], "activa"
        # algunos servers no aceptan HEAD; reintento con GET range corto
        if r.status_code in (405, 501):
            r = requests.get(offer["link"], headers={**HEADERS, "Range": "bytes=0-512"}, timeout=8)
            if r.status_code < 400:
                return offer["id"], "activa"
        return offer["id"], "vencida"
    except Exception:
        return offer["id"], "vencida"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-workers", type=int, default=16)
    args = ap.parse_args()

    if not OFFERS_PATH.exists():
        print(f"sin offers.json en {OFFERS_PATH}, nada que validar", file=sys.stderr)
        return

    offers = json.loads(OFFERS_PATH.read_text(encoding="utf-8"))
    print(f"validating {len(offers)} offers", file=sys.stderr)

    started = time.time()
    results: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futs = [ex.submit(check, o) for o in offers]
        for f in as_completed(futs):
            oid, estado = f.result()
            results[oid] = estado

    activas = sum(1 for v in results.values() if v == "activa")
    vencidas = sum(1 for v in results.values() if v == "vencida")
    elapsed = time.time() - started

    for o in offers:
        if o["id"] in results:
            o["estado"] = results[o["id"]]
            o["last_checked"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    tmp = OFFERS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(offers, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OFFERS_PATH)

    print(f"done · {activas} activas · {vencidas} vencidas · {elapsed:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
