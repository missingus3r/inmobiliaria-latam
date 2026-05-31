// scrape_pycomx.mjs — scrape new listings for PY (InfoCasas), CO (Fincaraiz), MX (Lamudi)
// Output: JSON array of offers in offers.json schema. id = sha1(link)[:12].
import puppeteer from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import crypto from "crypto";
puppeteer.use(StealthPlugin());

const CHROME = "/usr/bin/google-chrome";
const UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";
const sha1 = s => crypto.createHash("sha1").update(s).digest("hex").slice(0, 12);
const sleep = ms => new Promise(r => setTimeout(r, ms));

// InfoCasas-network targets (PY=infocasas.com.py, CO=fincaraiz.com.co) share __NEXT_DATA__ shape.
const IC_TARGETS = [
  { country: "PY", base: "https://www.infocasas.com.py", paths: ["/venta/casas-y-apartamentos", "/venta/casas-y-apartamentos/pagina2", "/alquiler/casas-y-apartamentos"] },
  { country: "CO", base: "https://www.fincaraiz.com.co", paths: ["/venta/casas-y-apartamentos", "/venta/casas-y-apartamentos/pagina2", "/arriendo/casas-y-apartamentos"] },
];
// Lamudi MX uses JSON-LD ItemList.
const LAMUDI_TARGETS = [
  { country: "MX", urls: ["https://www.lamudi.com.mx/casa/for-sale/", "https://www.lamudi.com.mx/departamento/for-sale/", "https://www.lamudi.com.mx/casa/for-rent/"] },
];

function mapCurrency(name) {
  if (!name) return "USD";
  const n = name.trim();
  if (/U\$S|US\$|USD|u\$d/i.test(n)) return "USD";
  if (n === "$") return null; // ambiguous, resolved per-country
  if (/Gs|₲/i.test(n)) return "PYG";
  return null;
}

function priceFromText(txt) {
  if (!txt) return { price: null, currency: null };
  // try "$5,750,000" or "USD 250,000" etc
  let m = txt.match(/(USD|U\$S|US\$|MXN|MN)\s*\$?\s*([\d.,]{4,})/i);
  if (m) { return { price: parseFloat(m[2].replace(/[.,](?=\d{3}\b)/g, "")) || null, currency: /USD|U\$S|US\$/i.test(m[1]) ? "USD" : "MXN" }; }
  m = txt.match(/\$\s*([\d][\d.,]{4,})/);
  if (m) { return { price: parseFloat(m[1].replace(/[.,](?=\d{3}\b)/g, "")) || null, currency: null }; }
  return { price: null, currency: null };
}

async function setup(browser) {
  const page = await browser.newPage();
  await page.setUserAgent(UA);
  await page.setViewport({ width: 1920, height: 1080 });
  await page.setExtraHTTPHeaders({ "Accept-Language": "es;q=0.9,en;q=0.8" });
  return page;
}

async function scrapeIC(page, base, path, country) {
  const url = base + path;
  const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 35000 });
  const status = resp ? resp.status() : 0;
  await sleep(4000);
  if (status !== 200) { console.error(`    ${url} status=${status}`); return []; }
  const nd = await page.evaluate(() => document.getElementById("__NEXT_DATA__")?.textContent || "");
  if (!nd) { console.error(`    ${url} no __NEXT_DATA__`); return []; }
  let data;
  try { data = JSON.parse(nd); } catch (e) { console.error(`    ${url} NEXT parse err`); return []; }
  const list = data?.props?.pageProps?.fetchResult?.searchFast?.data;
  if (!Array.isArray(list)) { console.error(`    ${url} no searchFast.data`); return []; }
  const operation = /alquiler|arriendo/i.test(path) ? "Alquiler" : "Venta";
  const out = [];
  for (const r of list) {
    if (!r || r.draft || r.deleted || r.sold) continue;
    if (!r.link || r.price?.hidePrice) continue;
    const link = r.link.startsWith("http") ? r.link : base + (r.link.startsWith("/") ? r.link : "/" + r.link);
    const amount = r.price?.amount ?? null;
    if (!amount) continue;
    let currency = mapCurrency(r.price?.currency?.name);
    if (currency === null) currency = country === "CO" ? "COP" : (country === "PY" ? "PYG" : "USD");
    out.push({
      id: sha1(link), country,
      operation: r.operation_type?.name || operation,
      class: r.property_type?.name || "Apartamento",
      title: String(r.title || "").slice(0, 200),
      price: amount, currency, link,
      platform: new URL(base).hostname.replace(/^www\./, ""),
      location: r.address || "",
      bedrooms: r.bedrooms ?? null,
      bathrooms: r.bathrooms ?? null,
      area_m2: r.m2Built ?? r.m2 ?? null,
      images: r.img ? [r.img] : [],
      estado: "activa",
      fetched_at: new Date().toISOString(),
      source: "scrape:infocasas-next",
    });
  }
  console.error(`    ${url} -> ${out.length} listings`);
  return out;
}

async function scrapeLamudi(page, url, country) {
  const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 35000 });
  const status = resp ? resp.status() : 0;
  await sleep(4000);
  if (status !== 200) { console.error(`    ${url} status=${status}`); return []; }
  const lds = await page.evaluate(() => [...document.querySelectorAll('script[type="application/ld+json"]')].map(s => s.textContent));
  const operation = /for-rent|renta/i.test(url) ? "Alquiler" : "Venta";
  const out = [];
  for (const raw of lds) {
    let d; try { d = JSON.parse(raw); } catch (e) { continue; }
    const arr = Array.isArray(d) ? d : [d];
    for (const node of arr) {
      const graph = node["@graph"] || [node];
      for (const g of graph) {
        const me = g.mainEntity;
        if (!Array.isArray(me)) continue;
        for (const ml of me) {
          for (const li of (ml.itemListElement || [])) {
            const it = li.item; if (!it) continue;
            const link = it["@id"] || it.url; if (!link) continue;
            const { price, currency } = priceFromText(it.description);
            out.push({
              id: sha1(link), country,
              operation,
              class: /apartment|departamento/i.test(it["@type"] || "") ? "Apartamento" : "Casa",
              title: String(it.name || "").slice(0, 200),
              price, currency: currency || "MXN", link,
              platform: "lamudi.com.mx",
              location: it.address?.streetAddress || it.address?.addressLocality || "",
              bedrooms: it.numberOfBedrooms ?? null,
              bathrooms: it.numberOfBathroomsTotal ?? null,
              area_m2: it.floorSize?.value ? parseFloat(it.floorSize.value) : null,
              images: it.image ? [it.image] : [],
              estado: "activa",
              fetched_at: new Date().toISOString(),
              source: "scrape:lamudi-jsonld",
            });
          }
        }
      }
    }
  }
  console.error(`    ${url} -> ${out.length} listings`);
  return out;
}

const browser = await puppeteer.launch({
  executablePath: CHROME, headless: "new",
  args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled", "--lang=es", "--window-size=1920,1080"],
});
const all = [];
for (const t of IC_TARGETS) {
  for (const p of t.paths) {
    const page = await setup(browser);
    try { console.error(`==> ${t.country} ${t.base}${p}`); all.push(...await scrapeIC(page, t.base, p, t.country)); }
    catch (e) { console.error(`    error: ${e.message}`); }
    finally { await page.close(); }
  }
}
for (const t of LAMUDI_TARGETS) {
  for (const u of t.urls) {
    const page = await setup(browser);
    try { console.error(`==> ${t.country} ${u}`); all.push(...await scrapeLamudi(page, u, t.country)); }
    catch (e) { console.error(`    error: ${e.message}`); }
    finally { await page.close(); }
  }
}
await browser.close();
// dedup within scrape by id
const seen = new Set(); const dedup = [];
for (const o of all) { if (seen.has(o.id)) continue; seen.add(o.id); dedup.push(o); }
process.stdout.write(JSON.stringify(dedup, null, 2));
