# LatamHouse

Hub agregador de listings inmobiliarios LATAM. Datos abiertos, sin servidor, sin login. UY · AR · PY · CL · MX · CO.

🌐 Demo local: `http://127.0.0.1:8765` (correr `python3 -m http.server 8765` desde la raíz).

---

## Cómo funciona

```
[fuentes ~283]
     ↓
Friday + N agentes Task en paralelo (Sonnet)
     ↓
data/offers.json + assets/images/<id>.<ext>
     ↓
backend/validator.py — HEAD a cada link → marca "vencida" si 4xx/5xx
     ↓
git commit + push
     ↓
front estático (index.html) lee data/offers.json directo
```

- **Sin backend en runtime**: el front es 100% estático. Solo lee `data/offers.json`.
- **Sin login, sin tracking**: los favoritos viven en `localStorage` del navegador. Banner avisa al usuario al primer uso.
- **i18n**: ES y PT (toggle en navbar).
- **Tema**: claro / oscuro (persistido en localStorage).
- **Geo**: detecta país por IP (Cloudflare trace `1.1.1.1/cdn-cgi/trace`); selector manual en navbar.
- **Moneda**: la del país seleccionado (UYU/USD, ARS/USD, PYG, CLP/UF, MXN, COP).

## Pipeline de scraping

El scraping no usa Python + requests + OpenAI. Lo hace **Friday** (Claude Code) con agentes Task en paralelo:

1. Cron diario (`cron-prompts.md §24` — `scrape-inmobiliaria`) dispara prompt a Friday.
2. Friday lee `data/sources_full.json`, particiona los ~283 portales en chunks.
3. Lanza N agentes `Task(subagent_type=general-purpose)` en paralelo, cada uno toma su chunk:
   - `WebFetch` cada URL del chunk.
   - Si la URL responde con 403/captcha (Cloudflare WAF), invoca el fallback headless: `node backend/headless_scraper.js <url>` que usa Chrome con stealth-plugin.
   - Extrae listings (título, precio, moneda, dorms, área, ubicación, link, foto).
   - Devuelve JSON.
4. Friday merge + dedupe (`id = sha1(link)[:12]`) en `data/offers.json`.
5. Friday descarga primera imagen de cada listing nuevo a `assets/images/<id>.<ext>`.
6. Corre `backend/pipeline.sh` (validator + commit + push).

Los agentes corren con **Sonnet** para optimizar costos vs Opus.

### Headless scraper (`backend/headless_scraper.js`)

Fallback Chrome+Stealth para portales con anti-bot agresivo. Uso:

```bash
node backend/headless_scraper.js [--mode=extract|html] <url1> [url2] ...
```

- `--mode=extract` (default): intenta extraer listings con heurística (JSON-LD, microdata, selectores comunes). Output: JSON array de listings con el mismo schema que el frontend espera.
- `--mode=html`: solo navega y devuelve `{url, status, title, body_len, text}`. Útil cuando un agente downstream va a hacer la extracción con LLM (más robusto a layouts custom).

**Cobertura observada** (08/05/2026):
- ✅ Bypass funciona: Zonaprop (intermitente), MercadoLibre AR (~48 listings), MercadoLibre UY/CL.
- ⚠️ Cloudflare interactive challenge: Argenprop, Properati AR/CL — siguen requiriendo residential proxy.
- ⚠️ Layouts custom (Infocasas, Gallito, TocToc, Portal Inmobiliario): status 200 pero selectores genéricos no matchean → usar `--mode=html` y dejar al LLM extraer.

**Stack**: `puppeteer-core` + `puppeteer-extra` + `puppeteer-extra-plugin-stealth`. Usa Chrome del sistema (`/usr/bin/google-chrome`) — no descarga binario propio.

## Stack

- **Front**: HTML/CSS/JS vanilla, single file `index.html` (~700 líneas)
- **Datos**: `data/sources_full.json` + `data/offers.json` + `assets/images/`
- **Backend**: Python 3 stdlib + `requests` (`backend/validator.py` y `backend/parse_sources.py`); Node 22 + `puppeteer-core` + `puppeteer-extra` + stealth plugin (`backend/headless_scraper.js` para portales con WAF)
- **Pipeline**: `backend/pipeline.sh` (validator + commit + push)
- **Scraping orchestration**: Friday + crons en `~/.claude/cron-prompts.md`

## Estructura

```
inmobiliaria-latam/
├── index.html              # SPA single-file
├── favicon.svg             # icono casa
├── data/
│   ├── sources_full.json   # 283 fuentes (UY: 49 portales + 16 containers + 194 inmobiliarias; resto: top 4-5 por país)
│   └── offers.json         # listings actuales (refresh diario)
├── assets/
│   └── images/             # primer thumb de cada listing
├── backend/
│   ├── parse_sources.py    # genera sources_full.json desde el .txt original
│   ├── validator.py        # HEAD a cada link → estado: activa | vencida
│   └── pipeline.sh         # validator + commit + push
└── README.md
```

## Correr local

```bash
cd ~/proyectos/inmobiliaria-latam
python3 -m http.server 8765
# abrir http://127.0.0.1:8765
```

(El servidor se levanta automáticamente al iniciar Friday — ver `~/.claude/CLAUDE.md` paso 23 del Session Startup.)

## Fuentes

### Uruguay (49 portales + 16 containers + 194 inmobiliarias)

#### Portales / clasificados / desarrolladoras

Sigaloavarela · Puntoinmobiliario · Altiusgroup · Propiedadesensoriano · Propiedadesendurazno · Propiedadesmontevideo · Mercadolibre · Infocasas · Gallito · Inmobiliariaimperial · Braglia · Campiglia · Inmobiliariabelvedere · Inmobiliariaroig · Aliveresidences · Modernapropiedades · Prop · Sacradalmas · Vitriumcapital · Crisciblanco · Caladelyacht · Fendichateaupunta · Metdesarrollos · Nanalavagna · Winks · Exa · Newland · Grou · Grourambla · Drhousebienesraices · Criba · Lagom · Gary-otto · Vinsoca · Ezmaconstrucciones · Quierocasa · Mympropiedades · Inmobiliariamillenium · Pma-realestate · Realedo · Baconstrucciones · Bdp · Hermidapropiedades · Piresbenlian · Remax · Torrescardinal · Rossanabonora · Everesturuguay · Lascampanas

#### Containers

LP House Container · Multicontainer · Pluscontainer · Mister Construcciones · Eleve · Tu Casa Container · Living Containers · Decotainer · Home Containers Uruguay · Agrocontainers · Zonacontainer · Decasur House · Total Containers · Atlantic Containers · Berardi Propiedades · Zapata

#### Inmobiliarias listadas (194 total)

Lista completa en `data/sources_full.json` campo `countries.UY.inmobiliarias`. Extracto: A.C.R. · Abacos · Abrehaus · Acapulco · Acerenza & Amestoy · Adi · Agata · Agora · Aguilera · Agustín García Helguera · Alhambra · Alianza · Alicia Rubio · Ananikian · Anfil · Antares · Anval · Aqui-techo · Arbeleche Bessonart · Arditti · Arkontes · Arteaga Hill · Atenea · Atlantica Castells · Aval · Ayarza · Balvi · Bernasconi · Bien Seguro · Blegio · Breccia · Bruno · Buysan · Cajarville · Caldeyro Stajano · Calero · Canepa & Canepa · Carmel · Carmen Martínez · Carolina Núñez · Casatroja · Castello · Catañy · Cetrangolo · Christophersen · Ciudad · Claudio Poggio · Company & Romero · Crisci Blanco · Cristina Ottonello · CRITERIO · Dario D'angelo · Daver · De Arteaga · Deambrosis · Del Rey · Di Matteo · Domus · Duque · Echeverria y Olivera · El Faro · Elina Buela · Equipo Cuatro · Estudio Amay · Estudio VIP · Fachola · Fascioli · Foti · Fraga · Franco · Frattini & Mocchi · Frechou · G y S · Gameroni · Garcia – Vidal · Gianelli · Giletti · Heide · Inciarte · Budi · Dobal · Duner · GASALLA · Gorga · Ibiza · Milenio · Monymar · Passadore · Tropical · Iocco · Irazabal · Juan Pedro Molla · Juan Ruiz · Kosak · Laporte · Lariau · Lars · Lebutt · Lorieto · Mª Jesús Etcheverry · Maissonave · Marcel Sapin · Mariela Rodriguez · Meikle · Meridiano · Miranda · Mones Roses · Murar · Muzio · MVD · Nexo · Norberto Canepa · Oficentro · Padin · Pallares Bruzzone · Parietti · Parodi · Pedragosa · Perez del Castillo · Piaza · Pilar Cibils · Pilar Quartino · Piloni · Piria · Prego · Promociones y Servicios · Raymond · Reyes Ruano · Robert · Roisecco · Rosario Roig · Rossana Bonora · Salustio · Sayago · Scarpelli · Sendeza · SIAB · Silvana Crosato · Soares Netto · Sosa · Spazio · Taranto · Teca · TOBIMAC · Trieme · Triham · Varela · Vargas · Verónica Cánepa · Vilanova · Villamide · Viturro · Walter Passadore · Yaquinta · Yasmine Cóccaro · Yudka · Zilberman · …

### Argentina (5)
Zonaprop · Argenprop · MercadoLibre · Properati AR · InmoUp

### Paraguay (4)
InfoCasas PY · Clasipar · Properati PY · Mi Casa Py

### Chile (5)
Portal Inmobiliario · MercadoLibre CL · Yapo · TocToc · Properati CL

### México (5)
Inmuebles24 · Vivanuncios · Lamudi MX · MercadoLibre MX · Casas y Terrenos

### Colombia (5)
Metrocuadrado · Fincaraiz · Properati CO · MercadoLibre CO · Lamudi CO

## Roadmap

| Versión | Estado | Contenido |
|---|---|---|
| **V1.0** | en curso | Casas / Aptos / Containers UY + AR/PY/CL/MX/CO |
| V1.1 | pendiente | Cooperativas de vivienda UY (info MVOTMA, FUCVAM, FECOVI) |
| V1.2 | pendiente | Asistente IA (chatbot consultivo, opt-in) |
| V2.0 | pendiente | Préstamos: bancos, Nubank, cooperativas, financieras |
| V3.0 | pendiente | Centros de estudio + ads |
| V4.0 | pendiente | Autos |
| V4.5 | pendiente | Empleos (cargo, salario, modalidad) y carreras universitarias/online |
| V5.0+ | pendiente | Expansión LATAM full |

## Privacidad

- No hay servidor que reciba tus datos.
- Favoritos: `localStorage` del navegador (limpiar cookies → se pierden).
- Tema, idioma y país: `localStorage`.
- Geo IP: solo en cliente, vía Cloudflare trace; no se envía a ningún servidor nuestro.

## Licencia

MIT.
