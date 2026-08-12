#!/usr/bin/env python3
"""validator.py — verifica que los links de offers.json sigan vivos.

Para cada offer:
  - HEAD request al link (timeout 8s)
  - 2xx/3xx → estado="activa"
  - 404/410 → estado="vencida" (el aviso se dio de baja de verdad)
  - 401/403/405/429 → NO se toca el estado previo: eso es anti-bot, no baja
    (proposal #38 — el 31/07 marcó vencidos 26 de 27 avisos de vivanuncios.com.mx
    por 403 del anti-bot, corrompiendo offers.json). Se anota `last_block`.
  - resto de 4xx/5xx o timeout → estado="vencida"

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

# proposal #38: un 4xx no es un solo hecho. 404/410 = el aviso ya no está;
# 401/403/429 = el portal nos bloqueó y no sabemos nada del aviso.
GONE = {404, 410}
BLOCKED = {401, 403, 405, 429}


def check(offer: dict) -> tuple[str, str | None, int | None]:
    """Return (id, new_estado | None, blocked_status | None).

    new_estado None significa «no sabemos»: el caller conserva el estado previo."""
    try:
        r = requests.head(offer["link"], headers=HEADERS, timeout=8, allow_redirects=True)
        if r.status_code < 400:
            return offer["id"], "activa", None
        # algunos servers no aceptan HEAD; reintento con GET range corto
        if r.status_code in (405, 501):
            r = requests.get(offer["link"], headers={**HEADERS, "Range": "bytes=0-512"}, timeout=8)
            if r.status_code < 400:
                return offer["id"], "activa", None
        if r.status_code in GONE:
            return offer["id"], "vencida", None
        if r.status_code in BLOCKED:
            return offer["id"], None, r.status_code
        return offer["id"], "vencida", None
    except Exception:
        return offer["id"], "vencida", None


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
    blocked: dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futs = [ex.submit(check, o) for o in offers]
        for f in as_completed(futs):
            oid, estado, block = f.result()
            if estado is not None:
                results[oid] = estado
            if block is not None:
                blocked[oid] = block

    activas = sum(1 for v in results.values() if v == "activa")
    vencidas = sum(1 for v in results.values() if v == "vencida")
    elapsed = time.time() - started

    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    for o in offers:
        if o["id"] in results:
            o["estado"] = results[o["id"]]
            o["last_checked"] = now
        if o["id"] in blocked:
            # estado intacto a propósito: sólo dejamos rastro del bloqueo
            o["last_block"] = f"{blocked[o['id']]}@{now}"
            o["last_checked"] = now

    tmp = OFFERS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(offers, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OFFERS_PATH)

    print(f"done · {activas} activas · {vencidas} vencidas · "
          f"{len(blocked)} bloqueadas (estado sin tocar) · {elapsed:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
