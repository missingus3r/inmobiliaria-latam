#!/usr/bin/env node
// headless_scraper.js — fallback Chrome+Stealth para portales con anti-bot WAF.
//
// Uso:
//   node backend/headless_scraper.js [--mode=extract|html] <url1> [url2]...
//
//   --mode=extract  (default) — intenta extraer listings con heurística
//                   (JSON-LD, microdata, selectores comunes). Output: JSON
//                   array de listings.
//
//   --mode=html     — solo navega y devuelve {url, status, title, html_text}
//                   por URL. Útil cuando un agente downstream va a hacer la
//                   extracción con LLM. html_text es innerText del body
//                   (no HTML crudo) para mantener tamaño manejable.
//
// Requisitos:
//   - Google Chrome en /usr/bin/google-chrome
//   - puppeteer-core + puppeteer-extra + puppeteer-extra-plugin-stealth
//
// Limitaciones conocidas:
//   - Cloudflare interactive challenge (Zonaprop, Argenprop full WAF) puede
//     seguir devolviendo 403 / "Un momento…" interstitial aún con stealth.
//     Para esos sitios la solución de fondo es residential proxy.

import puppeteer from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import core from "puppeteer-core";
import crypto from "crypto";
import { URL } from "url";

puppeteer.use(StealthPlugin());

const CHROME = "/usr/bin/google-chrome";
const UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";

function sha1Short(s) {
  return crypto.createHash("sha1").update(s).digest("hex").slice(0, 12);
}

function inferCountryFromUrl(url) {
  if (/\.uy[/?#]?|\.com\.uy/.test(url)) return "UY";
  if (/\.ar[/?#]?|\.com\.ar/.test(url)) return "AR";
  if (/\.py[/?#]?|\.com\.py/.test(url)) return "PY";
  if (/\.cl[/?#]?|\.com\.cl/.test(url)) return "CL";
  if (/\.mx[/?#]?|\.com\.mx/.test(url)) return "MX";
  if (/\.co[/?#]?|\.com\.co/.test(url)) return "CO";
  return "UY";
}

function inferOperation(text) {
  const t = (text || "").toLowerCase();
  if (/alquil|aluga|aluguel|rent/.test(t)) return "Alquiler";
  return "Venta";
}

function inferClass(text) {
  const t = (text || "").toLowerCase();
  if (/contain/.test(t)) return "Container";
  if (/casa|house/.test(t)) return "Casa";
  return "Apartamento";
}

async function setupPage(browser) {
  const page = await browser.newPage();
  await page.setUserAgent(UA);
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.setExtraHTTPHeaders({
    "Accept-Language": "es-UY,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
  });
  return page;
}

async function navigateAndStabilize(page, url) {
  const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 35000 });
  const status = resp ? resp.status() : 0;
  // give time for client-side JS + any CF challenge
  await new Promise(r => setTimeout(r, 5000));
  // scroll mid-page to trigger lazy-load
  try {
    await page.evaluate(() => { window.scrollTo(0, document.body.scrollHeight / 3); });
    await new Promise(r => setTimeout(r, 1500));
    await page.evaluate(() => { window.scrollTo(0, (document.body.scrollHeight * 2) / 3); });
    await new Promise(r => setTimeout(r, 1000));
  } catch (e) { /* ignore */ }
  return status;
}

async function extractListings(page, url) {
  const country = inferCountryFromUrl(url);
  const platform = new URL(url).hostname.replace(/^www\./, "");
  const results = [];

  // Heurística 1: JSON-LD con Product/Offer/RealEstateListing
  const jsonLdHits = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
      try {
        const d = JSON.parse(s.textContent);
        const arr = Array.isArray(d) ? d : (d["@graph"] ? d["@graph"] : [d]);
        arr.forEach(it => {
          if (!it || typeof it !== "object") return;
          const t = JSON.stringify(it["@type"] || "");
          if (/Product|Offer|RealEstate|Apartment|House|Residence|SingleFamilyResidence/i.test(t)) {
            out.push(it);
          }
        });
      } catch (e) {}
    });
    return out;
  });

  for (const p of jsonLdHits) {
    const offers = p.offers ? (Array.isArray(p.offers) ? p.offers : [p.offers]) : [];
    const offer = offers[0] || p;
    const price = parseFloat(offer.price ?? offer.priceSpecification?.price ?? p.price ?? 0) || 0;
    if (!price) continue;
    const currency = offer.priceCurrency ?? offer.priceSpecification?.priceCurrency ?? "USD";
    const link = p.url ?? offer.url ?? url;
    const image = (Array.isArray(p.image) ? p.image[0] : p.image) ?? "";
    const title = p.name ?? offer.name ?? "";
    if (!title) continue;
    results.push({
      id: sha1Short(link),
      country,
      operation: inferOperation(title + " " + url),
      class: inferClass(title),
      title: String(title).slice(0, 200),
      price,
      currency,
      link,
      platform,
      location: p.address?.addressLocality ?? p.address?.streetAddress ?? "",
      bedrooms: p.numberOfRooms ?? null,
      bathrooms: p.numberOfBathroomsTotal ?? null,
      area_m2: p.floorSize?.value ?? null,
      images: image ? [image] : [],
      estado: "activa",
      fetched_at: new Date().toISOString(),
      source: "headless:jsonld",
    });
  }

  // Heurística 2: cards visibles si JSON-LD no aportó
  if (results.length === 0) {
    const cards = await page.evaluate(() => {
      const sels = [
        '[data-qa="posting CARD"]',
        '.postingCardLayout-module__posting-card-container',
        '.postings-container article',
        '.ui-search-result',
        '.listing-card', '.PropertyCard', '.property-card',
        'article[itemtype*="Product"]', 'article[itemtype*="Residence"]',
        'a[href*="/inmueble/"], a[href*="/propiedad/"], a[href*="/detalle/"]',
      ];
      const found = [];
      const seen = new Set();
      for (const sel of sels) {
        const els = document.querySelectorAll(sel);
        if (els.length === 0) continue;
        els.forEach(el => {
          const a = el.matches("a[href]") ? el : el.querySelector("a[href]");
          if (!a) return;
          const link = new URL(a.href, location.href).href;
          if (seen.has(link)) return;
          seen.add(link);
          const text = el.innerText.replace(/\s+/g, " ").slice(0, 500);
          const img = el.querySelector("img");
          const imgSrc = img?.src || img?.dataset?.src || img?.dataset?.lazy || "";
          const priceMatch = text.match(/(?:USD|U\$S|US\$|\$U\b|\$)\s*([\d.,]+)/i);
          let price = 0, currency = "USD";
          if (priceMatch) {
            const raw = priceMatch[1].replace(/\./g, "").replace(",", ".");
            price = parseFloat(raw);
            if (/U\$S|USD|US\$/i.test(priceMatch[0])) currency = "USD";
            else if (/\$U\b/.test(priceMatch[0])) currency = "UYU";
            else currency = "USD";
          }
          const title = el.querySelector("h2,h3,.posting-title,.title")?.innerText?.trim() || text.slice(0, 80);
          const bedM = text.match(/(\d+)\s*(?:dorm|hab|cuarto|recám|bed|amb)/i);
          const areaM = text.match(/(\d+(?:[.,]\d+)?)\s*m[²2]/i);
          const loc = el.querySelector(".posting-location,.location,.address,[itemprop='address']")?.innerText?.trim() || "";
          found.push({
            link, text, imgSrc, title: title.slice(0, 200), price, currency,
            bedrooms: bedM ? parseInt(bedM[1]) : null,
            area_m2: areaM ? parseFloat(areaM[1].replace(",", ".")) : null,
            location: loc,
          });
        });
        if (found.length > 0) break;
      }
      return found.slice(0, 12);
    });

    for (const c of cards) {
      if (!c.title || !c.price) continue;
      results.push({
        id: sha1Short(c.link),
        country,
        operation: inferOperation(c.text + " " + url),
        class: inferClass(c.title + " " + c.text),
        title: c.title,
        price: c.price,
        currency: c.currency,
        link: c.link,
        platform,
        location: c.location,
        bedrooms: c.bedrooms,
        bathrooms: null,
        area_m2: c.area_m2,
        images: c.imgSrc ? [c.imgSrc] : [],
        estado: "activa",
        fetched_at: new Date().toISOString(),
        source: "headless:cards",
      });
    }
  }

  return results;
}

async function dumpHtml(page, url) {
  const data = await page.evaluate(() => ({
    title: document.title,
    bodyLen: document.body?.innerText?.length || 0,
    text: document.body?.innerText?.slice(0, 60000) || "",
  }));
  return { url, title: data.title, body_len: data.bodyLen, text: data.text };
}

async function main() {
  const argv = process.argv.slice(2);
  const mode = argv.find(a => a.startsWith("--mode="))?.split("=")[1] || "extract";
  const urls = argv.filter(a => !a.startsWith("--"));
  if (urls.length === 0) {
    console.error("uso: node headless_scraper.js [--mode=extract|html] <url> [url] ...");
    process.exit(1);
  }

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: "new",
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-blink-features=AutomationControlled",
      "--lang=es-UY",
      "--window-size=1920,1080",
    ],
  });

  const all = [];
  for (const url of urls) {
    const page = await setupPage(browser);
    let status = 0;
    try {
      console.error(`==> ${url}`);
      status = await navigateAndStabilize(page, url);
      console.error(`    status=${status}`);
      if (mode === "html") {
        const out = await dumpHtml(page, url);
        out.status = status;
        all.push(out);
      } else {
        const items = await extractListings(page, url);
        console.error(`    ${items.length} listings`);
        all.push(...items);
      }
    } catch (e) {
      console.error(`    error: ${e.message}`);
    } finally {
      await page.close();
    }
  }

  await browser.close();
  process.stdout.write(JSON.stringify(all, null, 2));
}

main();
