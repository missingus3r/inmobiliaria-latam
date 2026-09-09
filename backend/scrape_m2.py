#!/usr/bin/env python3
"""Scrape metrocuadrado.com (CO) search pages -> offers.json schema rows."""
import re, json, hashlib, sys, time
import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
HDRS = {"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9"}
BASE = "https://www.metrocuadrado.com"

def sha1_12(s): return hashlib.sha1(s.encode()).hexdigest()[:12]

def flight(html):
    buf = []
    for c in re.findall(r'self\.__next_f\.push\(\[1,\s*(".*?")\]\)', html, re.S):
        try: buf.append(json.loads(c))
        except Exception: pass
    return "".join(buf)

def extract_results(text):
    out = []
    for m in re.finditer(r'"results"\s*:\s*\[', text):
        start = m.end() - 1
        depth, i, instr, esc = 0, start, False, False
        while i < len(text):
            ch = text[i]
            if instr:
                if esc: esc = False
                elif ch == "\\": esc = True
                elif ch == '"': instr = False
            else:
                if ch == '"': instr = True
                elif ch == "[": depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0: break
            i += 1
        try: arr = json.loads(text[start:i+1])
        except Exception: continue
        if isinstance(arr, list) and arr and isinstance(arr[0], dict) and "midinmueble" in arr[0]:
            out.extend(arr)
    return out

CLASS_MAP = {"Casa":"Casa","Apartamento":"Apartamento","Apartaestudio":"Apartamento",
             "Lote":"Terreno","Local":"Local","Oficina":"Oficina","Bodega":"Bodega",
             "Finca":"Finca","Consultorio":"Consultorio"}

def num(v):
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError): return None

def to_offer(r, now):
    link_rel = r.get("link") or (r.get("data") or {}).get("murldetalle")
    if not link_rel: return None
    link = link_rel if link_rel.startswith("http") else BASE + link_rel
    neg = (r.get("mtiponegocio") or "").lower()
    if "arriend" in neg:
        price, operation = r.get("mvalorarriendo"), "Alquiler"
    else:
        price, operation = r.get("mvalorventa"), "Venta"
    price = num(price)
    if not price or price <= 0: return None
    mid = r.get("midinmueble") or ""
    imgs = []
    for g in (r.get("mgaleriainmueble") or [])[:8]:
        if isinstance(g, str) and mid:
            imgs.append(f"https://multimedia.metrocuadrado.com/{mid}/{g}_p.jpg")
    prev = r.get("imageLink")
    if prev and prev not in imgs: imgs.insert(0, prev)
    loc = ", ".join([x for x in [
        r.get("mnombrecomunbarrio") or r.get("mbarrio"),
        (r.get("mzona") or {}).get("nombre"),
        (r.get("mciudad") or {}).get("nombre")] if x])
    ptype = ((r.get("mtipoinmueble") or {}).get("nombre") or "").strip()
    return {
        "id": sha1_12(link), "country": "CO", "source": "scrape:metrocuadrado-rsc",
        "platform": "metrocuadrado.com",
        "title": str(r.get("title") or "")[:200],
        "price": price, "currency": "COP",
        "operation": operation,
        "class": CLASS_MAP.get(ptype, ptype or "Apartamento"),
        "bedrooms": num(r.get("mnrocuartos")), "bathrooms": num(r.get("mnrobanos")),
        "area_m2": num(r.get("mareac")) or num(r.get("marea")),
        "location": loc, "link": link,
        "image_url": imgs[0] if imgs else None, "images": imgs,
        "estado": "activa", "fetched_at": now, "last_seen": now, "last_checked": now,
    }

def main():
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    seen, out = set(), []
    for path in sys.argv[1:]:
        url = BASE + path
        try: r = requests.get(url, headers=HDRS, timeout=45)
        except Exception as e:
            print(f"    {url} ERROR {e}", file=sys.stderr); continue
        if r.status_code != 200:
            print(f"    {url} status={r.status_code}", file=sys.stderr); continue
        res = extract_results(flight(r.text))
        n = 0
        for row in res:
            o = to_offer(row, now)
            if not o or o["id"] in seen: continue
            seen.add(o["id"]); out.append(o); n += 1
        print(f"    {url} -> {n} listings (raw {len(res)})", file=sys.stderr)
        time.sleep(3)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)

main()
