# CasaLatam — Demo

Agregador de listings inmobiliarios LATAM (UY, AR, PY) con asistente IA.

## Estructura

```
inmobiliaria-latam/
├── index.html          # SPA single-file (HTML+CSS+JS embebidos)
├── data/
│   ├── listings.json   # Mock data: 16 propiedades en UY/AR/PY
│   └── sources.json    # Fuentes: 10 portales (Infocasas, Zonaprop, etc)
└── README.md
```

## Correr local

```bash
cd ~/proyectos/inmobiliaria-latam
python3 -m http.server 8765
# abrir http://127.0.0.1:8765
```

## Secciones

- **Hero**: pitch + CTA
- **Áreas**: cards UY/AR/PY (filtran al hacer click)
- **Listings**: grid + filtros sticky (país, operación, tipo, dormitorios, precio, favs)
- **Cómo funciona**: diagrama Usuario↔App↔IA(brain+agentes)↔BD
- **Fuentes**: portales de origen
- **FAQ**: preguntas frecuentes

## Features

- 🔍 Buscador en navbar (debounced)
- ⭐ Favoritos (localStorage, requieren login)
- 👤 Login mock (cualquier user/pass — demo)
- 🤖 Asistente IA modal (mock con matching local — busca por país/tipo/precio/dorms)
- 📱 Responsive (filtros se reposicionan en mobile)

## Notas

- **Todo es demo**: no hay backend, no hay scraping real. La data es mock estática.
- El asistente IA hace pattern matching local sobre los listings para responder.
- En producción, el "brain" se conectaría al harness de scraping + LLM real.
