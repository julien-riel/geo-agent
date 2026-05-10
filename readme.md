# Géo-agent

Application web mono-utilisateur pour piloter des analyses spatiales sur les données WFS de Montréal via un agent local (Gemma 4 sur Ollama).

**Stack** : Next.js + LangGraph (Python) + CopilotKit + MapLibre + Ollama (local).

**Source des données** : `https://api.accept.montreal.ca/api/it-platforms/geomatic/wfs-maps/montreal/ows`

## Prérequis

- Python 3.12+, [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- [Ollama](https://ollama.com/) avec le modèle `gemma4:e4b` (`ollama pull gemma4:e4b`)

## Démarrage local (3 terminaux)

```bash
# 1. Ollama
ollama serve

# 2. Backend
cd backend
cp ../.env.example .env  # ajuster si besoin
uv sync --extra dev
uv run uvicorn geo_agent.main:app --reload  # http://localhost:8000

# 3. Frontend
cd frontend
npm install
npm run dev  # http://localhost:3000
```

## Usage

1. Ouvre http://localhost:3000
2. Clique "Dessiner zone" et trace un polygone (double-clic pour terminer)
3. Demande dans le chat : *"Trouve les chaussées dans cette zone"*
4. Coche le dataset dans le panneau du bas pour l'afficher sur la carte
5. Demande des analyses chaînées : *"Garde celles qui font plus de 200m, puis trouve les bâtiments à moins de 50m"*

## Tests

```bash
cd backend && uv run pytest          # tests unit + integration
cd backend && uv run pytest -m live  # tests qui frappent l'API WFS et Ollama (manuel)
cd frontend && npm test              # Vitest
cd frontend && npm run test:e2e      # Playwright
```

## Documentation

- `docs/superpowers/specs/2026-05-09-geo-agent-design.md` — spec complet
- `docs/superpowers/plans/2026-05-09-geo-agent.md` — plan d'implémentation

## Variables d'environnement

Voir `.env.example`. Variables clés :

| Variable | Défaut | Rôle |
|---|---|---|
| `OLLAMA_MODEL` | `gemma4:e4b` | Modèle Ollama. Tester `qwen2.5:7b` ou `llama3.1:8b` si tool calling défaillant |
| `MAX_FEATURES_PER_QUERY` | `5000` | Limite par requête WFS — au-delà, l'agent doit raffiner |
