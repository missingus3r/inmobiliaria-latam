#!/usr/bin/env python3
"""Parse PROYECTO HOMES.txt → data/sources_full.json.

Reads ~/.claude/channels/telegram/inbox/1778264716138-AgAD4gkAAryy8Ec.txt or
the path passed as $1, and produces structured data:

  - UY portales (the 80+ raw URLs in the txt's middle section)
  - UY containers (16 from the "CONTENEDORES:" section)
  - UY inmobiliarias listadas (300+ from the "Título:" lines)
  - AR/PY/CL/MX/CO: top portales conocidos (hardcoded — txt has none)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


TXT_DEFAULT = "/home/br1/.claude/channels/telegram/inbox/1778264716138-AgAD4gkAAryy8Ec.txt"

# AR/PY/CL/MX/CO — top portales (no están en el txt; van hardcoded)
KNOWN_PORTALES = {
    "AR": [
        {"name": "Zonaprop",     "url": "https://www.zonaprop.com.ar/",          "type": "Portal"},
        {"name": "Argenprop",    "url": "https://www.argenprop.com/",            "type": "Portal"},
        {"name": "MercadoLibre", "url": "https://inmuebles.mercadolibre.com.ar/", "type": "Marketplace"},
        {"name": "Properati AR", "url": "https://www.properati.com.ar/",         "type": "Portal"},
        {"name": "InmoUp",       "url": "https://www.inmoup.com.ar/",            "type": "Portal"},
    ],
    "PY": [
        {"name": "InfoCasas PY", "url": "https://www.infocasas.com.py/",  "type": "Portal"},
        {"name": "Clasipar",     "url": "https://clasipar.paraguay.com/", "type": "Clasificado"},
        {"name": "Properati PY", "url": "https://www.properati.com.py/",  "type": "Portal"},
        {"name": "Mi Casa Py",   "url": "https://www.micasa.com.py/",     "type": "Portal"},
    ],
    "CL": [
        {"name": "Portal Inmobiliario", "url": "https://www.portalinmobiliario.com/", "type": "Portal"},
        {"name": "MercadoLibre CL",     "url": "https://inmuebles.mercadolibre.cl/",  "type": "Marketplace"},
        {"name": "Yapo",                "url": "https://new.yapo.cl/",                "type": "Clasificado"},
        {"name": "TocToc",              "url": "https://www.toctoc.com/",             "type": "Portal"},
        {"name": "Properati CL",        "url": "https://www.properati.cl/",           "type": "Portal"},
    ],
    "MX": [
        {"name": "Inmuebles24",     "url": "https://www.inmuebles24.com/",     "type": "Portal"},
        {"name": "Vivanuncios",     "url": "https://www.vivanuncios.com.mx/",  "type": "Clasificado"},
        {"name": "Lamudi MX",       "url": "https://www.lamudi.com.mx/",       "type": "Portal"},
        {"name": "MercadoLibre MX", "url": "https://inmuebles.mercadolibre.com.mx/", "type": "Marketplace"},
        {"name": "Casas y Terrenos","url": "https://www.casasyterrenos.com/",  "type": "Portal"},
    ],
    "CO": [
        {"name": "Metrocuadrado",   "url": "https://www.metrocuadrado.com/",   "type": "Portal"},
        {"name": "Fincaraiz",       "url": "https://www.fincaraiz.com.co/",    "type": "Portal"},
        {"name": "Properati CO",    "url": "https://www.properati.com.co/",    "type": "Portal"},
        {"name": "MercadoLibre CO", "url": "https://inmuebles.mercadolibre.com.co/", "type": "Marketplace"},
        {"name": "Lamudi CO",       "url": "https://www.lamudi.com.co/",       "type": "Portal"},
    ],
}

CURRENCIES = {
    "UY": ("UYU", "USD"),
    "AR": ("ARS", "USD"),
    "PY": ("PYG", "USD"),
    "CL": ("CLP", "UF"),
    "MX": ("MXN", "USD"),
    "CO": ("COP", "USD"),
}

COUNTRY_NAME_ES = {
    "UY": "Uruguay",
    "AR": "Argentina",
    "PY": "Paraguay",
    "CL": "Chile",
    "MX": "México",
    "CO": "Colombia",
}


def domain(url: str) -> str:
    return urlparse(url).hostname or url


def parse_uy_portales(txt: str) -> list[dict]:
    """URLs sueltas en el bloque entre `LISTA DE SITIOS` y la sección Containers."""
    block_start = txt.find("LISTA DE SITIOS")
    if block_start == -1:
        block_start = 0
    block_end = txt.find("CONTENEDORES:")
    if block_end == -1:
        block_end = len(txt)
    block = txt[block_start:block_end]

    seen: set[str] = set()
    portales: list[dict] = []
    for url in re.findall(r"https?://[^\s\#]+", block):
        url = url.rstrip("/.,)")
        d = domain(url)
        if not d or d in seen:
            continue
        seen.add(d)
        # nombre legible: "infocasas.com.uy" → "Infocasas"
        slug = d.removeprefix("www.").split(".")[0]
        portales.append({
            "name": slug.capitalize(),
            "url": f"https://{d}/",
            "type": "Portal",
        })
    return portales


def parse_uy_containers(txt: str) -> list[dict]:
    block_start = txt.find("CONTENEDORES:")
    if block_start == -1:
        return []
    # corta hasta la próxima línea con "----" o "----"
    block_end = txt.find("\n----", block_start + 1)
    if block_end == -1:
        block_end = len(txt)
    block = txt[block_start:block_end]

    seen: set[str] = set()
    out: list[dict] = []
    for url in re.findall(r"https?://[^\s\#]+", block):
        url = url.rstrip("/.,)")
        d = domain(url)
        if not d or d in seen:
            continue
        seen.add(d)
        slug = d.removeprefix("www.").split(".")[0]
        out.append({
            "name": slug.capitalize(),
            "url": f"https://{d}/",
            "type": "Container",
        })
    return out


def parse_uy_inmobiliarias(txt: str) -> list[dict]:
    """Líneas `Título: <name>, Link: <link>, Imagen: <img>`."""
    out: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(
        r"Título:\s*(?P<name>[^,]+),\s*Link:\s*(?P<link>[^,]+),\s*Imagen:\s*(?P<img>[^\n]*)",
        txt,
    ):
        name = m.group("name").strip()
        link_raw = m.group("link").strip()
        img = m.group("img").strip()

        if name in seen:
            continue
        seen.add(name)

        url = None
        if link_raw and link_raw.lower() != "none":
            if not link_raw.startswith(("http://", "https://")):
                url = f"https://{link_raw}"
            else:
                url = link_raw

        entry = {"name": name, "url": url, "type": "Inmobiliaria"}
        if img:
            entry["logo"] = img
        out.append(entry)
    return out


def main() -> None:
    txt_path = Path(sys.argv[1] if len(sys.argv) > 1 else TXT_DEFAULT)
    txt = txt_path.read_text(encoding="utf-8")

    uy_portales = parse_uy_portales(txt)
    uy_containers = parse_uy_containers(txt)
    uy_inmobiliarias = parse_uy_inmobiliarias(txt)

    out: dict = {
        "generated_from": str(txt_path.name),
        "countries": {},
    }

    for code, (curr, curr_alt) in CURRENCIES.items():
        country_block = {
            "code": code,
            "name": COUNTRY_NAME_ES[code],
            "currency": curr,
            "currency_secondary": curr_alt,
            "portales": [],
            "containers": [],
            "inmobiliarias": [],
        }
        if code == "UY":
            country_block["portales"] = uy_portales
            country_block["containers"] = uy_containers
            country_block["inmobiliarias"] = uy_inmobiliarias
        else:
            country_block["portales"] = KNOWN_PORTALES[code]
        out["countries"][code] = country_block

    repo_root = Path(__file__).resolve().parent.parent
    target = repo_root / "data" / "sources_full.json"
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"wrote {target}")
    print(f"  UY: portales={len(uy_portales)} containers={len(uy_containers)} inmobiliarias={len(uy_inmobiliarias)}")
    for code in ("AR", "PY", "CL", "MX", "CO"):
        print(f"  {code}: portales={len(out['countries'][code]['portales'])}")


if __name__ == "__main__":
    main()
