#!/usr/bin/env python3
"""Scrape clasipar.paraguay.com (PY) inmuebles listing pages -> offers.json rows."""
import re, json, hashlib, sys, time, html as htmlmod
import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
HDRS = {"User-Agent": UA, "Accept-Language": "es-PY,es;q=0.9"}
BASE = "https://clasipar.paraguay.com"
LINK_RE = re.compile(r'https://clasipar\.paraguay\.com/inmuebles/([a-z0-9-]+)/([a-z0-9-]+-(\d{5,}))')

def sha1_12(s): return hashlib.sha1(s.encode()).hexdigest()[:12]

CLASS_MAP = {"casas":"Casa","departamentos":"Apartamento","terrenos":"Terreno",
             "locales-comerciales":"Local","oficinas":"Oficina","duplex":"Duplex",
             "quintas-y-estancias":"Quinta","edificios":"Edificio","depositos":"Deposito"}

def parse_price(txt):
    """'Gs. 1.345.000.000' | 'US$ 120.000' -> (price, currency)"""
    if not txt: return None, None
    t = htmlmod.unescape(txt).strip()
    cur = None
    if re.search(r'US\$|U\$S|USD', t, re.I): cur = "USD"
    elif re.search(r'Gs\.?|₲', t, re.I): cur = "PYG"
    m = re.search(r'([\d][\d.,]{2,})', t)
    if not m: return None, cur
    raw = m.group(1)
    # PY uses '.' as thousands separator
    digits = re.sub(r'[^\d]', '', raw)
    if not digits: return None, cur
    try: return int(digits), cur
    except ValueError: return None, cur

def cards(html):
    """Split the page into <article class="box-anuncio ..."> blocks."""
    parts = re.split(r'<article[^>]*class="[^"]*box-anuncio[^"]*"[^>]*>', html)
    return parts[1:]

def to_offer(block, now):
    m = LINK_RE.search(block)
    if not m: return None
    link, cat = m.group(0), m.group(1)
    # full title lives in title="..." of the titAnuncio anchor
    t = re.search(r'class="titAnuncio"[^>]*title="([^"]*)"', block)
    if not t:
        t = re.search(r'<a[^>]+href="' + re.escape(link) + r'"[^>]*title="([^"]*)"', block)
    title = htmlmod.unescape(t.group(1)).strip() if t else ""
    p = re.search(r'<p class="price">(.*?)</p>', block, re.S)
    price, currency = parse_price(p.group(1) if p else "")
    if not price: return None
    op = "Alquiler" if re.search(r'<strong>\s*Alquil', block, re.I) else "Venta"
    if op == "Venta" and re.search(r'\balquil', title, re.I): op = "Alquiler"
    img = re.search(r'<img[^>]+src="(//clasicdn\.paraguay\.com/[^"]+)"', block)
    image = ("https:" + img.group(1)) if img else None
    loc = re.search(r'/localidad:([a-z0-9-]+?)-\d+"[^>]*title="[^"]*"[^>]*>\s*([^<]+?)\s*</a>', block)
    location = htmlmod.unescape(loc.group(2)).strip() if loc else ""
    location = re.sub(r'^\w+\s+en\s+', '', location)
    return {
        "id": sha1_12(link), "country": "PY", "source": "scrape:clasipar-html",
        "platform": "clasipar.paraguay.com",
        "title": title[:200], "price": price, "currency": currency or "PYG",
        "operation": op, "class": CLASS_MAP.get(cat, cat.replace("-", " ").title()),
        "bedrooms": None, "bathrooms": None, "area_m2": None,
        "location": location, "link": link,
        "image_url": image, "images": [image] if image else [],
        "estado": "activa", "fetched_at": now, "last_seen": now, "last_checked": now,
    }

def main():
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    seen, out = set(), []
    for path in sys.argv[1:]:
        url = BASE + path
        try: r = requests.get(url, headers=HDRS, timeout=40)
        except Exception as e:
            print(f"    {url} ERROR {e}", file=sys.stderr); continue
        if r.status_code != 200:
            print(f"    {url} status={r.status_code}", file=sys.stderr); continue
        blocks = cards(r.text)
        n = 0
        for b in blocks:
            o = to_offer(b, now)
            if not o or o["id"] in seen: continue
            seen.add(o["id"]); out.append(o); n += 1
        print(f"    {url} -> {n} listings (raw cards {len(blocks)})", file=sys.stderr)
        time.sleep(2.5)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)

main()
