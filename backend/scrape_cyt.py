#!/usr/bin/env python3
"""Scrape casasyterrenos.com (MX) search pages -> offers.json schema rows."""
import re, json, hashlib, sys, time
import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
HDRS = {"User-Agent": UA, "Accept-Language": "es-MX,es;q=0.9"}
BASE = "https://www.casasyterrenos.com"

def sha1_12(s): return hashlib.sha1(s.encode()).hexdigest()[:12]

def flight(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*(".*?")\]\)', html, re.S)
    buf = []
    for c in chunks:
        try: buf.append(json.loads(c))
        except Exception: pass
    return "".join(buf)

def extract_props(text):
    """Find "properties":[...] and return parsed list (balanced-bracket scan)."""
    out = []
    for m in re.finditer(r'"properties"\s*:\s*\[', text):
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
        try:
            arr = json.loads(text[start:i+1])
        except Exception:
            continue
        if isinstance(arr, list) and arr and isinstance(arr[0], dict) and "canonical" in arr[0]:
            out.extend(arr)
    return out

TYPE_MAP = {"Casa":"Casa","Departamento":"Apartamento","Terreno":"Terreno",
            "Local":"Local","Oficina":"Oficina","Bodega":"Bodega","Rancho":"Rancho"}

def to_offer(p, now):
    if not isinstance(p, dict): return None
    slugs = p.get("slugs")
    canon = (slugs.get("canonical") if isinstance(slugs, dict) else None) or p.get("canonical")
    if not canon or not isinstance(canon, str): return None
    link = canon if canon.startswith("http") else BASE + canon
    is_sale = bool(p.get("isSale"))
    is_rent = bool(p.get("isRent"))
    if is_sale:
        price, operation = p.get("priceSale"), "Venta"
    elif is_rent:
        price, operation = p.get("priceRent"), "Alquiler"
    else:
        return None
    try: price = float(price)
    except (TypeError, ValueError): return None
    if not price or price <= 0: return None
    loc = ", ".join([x for x in [p.get("neighborhood"), p.get("municipality"), p.get("state")] if x])
    imgs = [i for i in (p.get("images") or []) if isinstance(i, str)][:8]
    prev = p.get("photoPreview")
    if prev and prev not in imgs: imgs.insert(0, prev)
    ptype = p.get("type") or ""
    return {
        "id": sha1_12(link), "country": "MX", "source": "scrape:casasyterrenos-rsc",
        "platform": "casasyterrenos.com",
        "title": str(p.get("name") or "")[:200],
        "price": int(price) if float(price).is_integer() else price,
        "currency": p.get("currency") or "MXN",
        "operation": operation,
        "class": TYPE_MAP.get(ptype, ptype or "Casa"),
        "bedrooms": p.get("rooms") or None,
        "bathrooms": p.get("bathrooms") or None,
        "area_m2": p.get("construction") or p.get("surface") or None,
        "location": loc, "link": link,
        "image_url": imgs[0] if imgs else None, "images": imgs,
        "estado": "activa", "fetched_at": now, "last_seen": now, "last_checked": now,
    }

def main():
    paths = sys.argv[1:]
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    seen, out = set(), []
    for path in paths:
        url = BASE + path
        try:
            r = requests.get(url, headers=HDRS, timeout=40)
        except Exception as e:
            print(f"    {url} ERROR {e}", file=sys.stderr); continue
        if r.status_code != 200:
            print(f"    {url} status={r.status_code}", file=sys.stderr); continue
        props = extract_props(flight(r.text))
        n = 0
        for p in props:
            try: o = to_offer(p, now)
            except Exception as e:
                print(f"      skip item: {e}", file=sys.stderr); continue
            if not o or o["id"] in seen: continue
            seen.add(o["id"]); out.append(o); n += 1
        print(f"    {url} -> {n} listings (raw {len(props)})", file=sys.stderr)
        time.sleep(2.5)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)

main()
