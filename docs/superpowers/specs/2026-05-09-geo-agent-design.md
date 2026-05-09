# Géo-agent — Design

**Date :** 2026-05-09
**Statut :** Approuvé pour planification
**Auteurs :** Julien Riel + Claude

## Résumé

Application web mono-utilisateur permettant à un utilisateur d'interagir en langage naturel avec les données géospatiales du serveur WFS de Montréal. L'utilisateur dessine un polygone sur une carte MapLibre, puis pilote un agent LangGraph (modèle local `gemma4:e4b` via Ollama) qui exécute des analyses spatiales et statistiques en chaînant les résultats. Les résultats sont persistés sur disque et référencés par ID/alias afin que l'agent ne charge jamais le GeoJSON dans son contexte.

Le stack est la voie officielle CopilotKit : Next.js (App Router) côté frontend, FastAPI + LangGraph côté backend, intégrés via le pattern CoAgent (état partagé en temps réel).

## Objectifs

1. Permettre des analyses spatiales pilotées par langage naturel sur les couches du WFS de Montréal
2. Supporter le chaînage d'opérations sans saturer la fenêtre de contexte de l'agent
3. Rester simple à exécuter localement (3 commandes : `ollama serve`, `uvicorn`, `next dev`)
4. Garder une architecture qui peut évoluer (déploiement, multi-utilisateur) sans réécriture

## Non-objectifs (MVP)

- Authentification, multi-utilisateur, déploiement
- Opérations géométriques avancées (union, dissolve, voronoi)
- Export téléchargeable des résultats
- Visualisation thématique avancée (choropleth, heatmap)
- Outil de dessin déclenché par l'agent (`request_polygon` — itération 2)

## Décisions clés (tranchées en brainstorming)

| Décision | Choix | Rationale |
|---|---|---|
| Scope analyses spatiales | Sélection + statistiques | Suffisant pour analyses chaînées utiles, raisonnable à implémenter |
| Découverte des couches WFS | Dynamique via GetCapabilities | Pas de config à maintenir, l'agent voit ce qui est dispo |
| Référence aux résultats | ID stable + alias sémantique | ID évite collisions, alias rend la conversation lisible |
| Pattern CopilotKit | CoAgent (`useCoAgent`) | État du graphe partagé en temps réel, generative UI |
| Flux d'interaction | Utilisateur dessine → demande (MVP), agent peut aussi demander un dessin (it. 2) | Plus simple à livrer, extensible |
| Déploiement | Local mono-utilisateur | Outil personnel, garde frontières propres |
| Gestion gros payloads WFS | Bbox requis + cap features (5000) | Double garde-fou, force le raffinement |
| Modèle | `gemma4:e4b` via Ollama, configurable par env | 8B avec tools + thinking, déjà installé |
| Layout UI | Carte plein écran + sidebar chat à droite + panneau datasets en bas | Pattern documenté CopilotKit, focus sur la carte |
| Calculs spatiaux | Filtre OGC poussé au WFS pour la sélection ; agrégations Python locales | Économise le réseau, exploite l'index serveur |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Browser                                                      │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Next.js (App Router)                                    │ │
│  │  ┌────────────────────────┐  ┌─────────────────────────┐ │ │
│  │  │ MapLibre + terra-draw  │  │ <CopilotSidebar>        │ │ │
│  │  │ - basemap fond-de-carte│  │ - chat                  │ │ │
│  │  │ - layers (datasets)    │  │ - useCoAgent state view │ │ │
│  │  │ - polygon drawing      │  │ - agent state renderers │ │ │
│  │  └────────────────────────┘  └─────────────────────────┘ │ │
│  │  ┌─────────────────────────────────────────────────────┐ │ │
│  │  │ Bottom panel : Datasets (alias → ID, count, bbox)   │ │ │
│  │  └─────────────────────────────────────────────────────┘ │ │
│  └────────────────────┬─────────────────────────────────────┘ │
│                       │ /api/copilotkit (Next API route)      │
└───────────────────────┼──────────────────────────────────────┘
                        │ LangGraph runtime (CopilotKit adapter)
                        ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI (Python)                                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  LangGraph agent (gemma4:e4b via Ollama)                 │ │
│  │  ┌─────────────┐ ┌───────────────┐ ┌──────────────────┐ │ │
│  │  │ tools:      │ │ state:        │ │ ChatOllama       │ │ │
│  │  │ list_layers │ │ datasets[]    │ │ tool_choice=auto │ │ │
│  │  │ select_     │ │ current_      │ │                  │ │ │
│  │  │   features  │ │   drawing     │ │                  │ │ │
│  │  │ aggregate   │ │ active_layers │ │                  │ │ │
│  │  │ filter_attrs│ │               │ │                  │ │ │
│  │  └─────────────┘ └───────────────┘ └──────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ services/                                                 │ │
│  │ ┌─────────────┐ ┌──────────────┐ ┌──────────────────┐  │ │
│  │ │ wfs_client  │ │ result_store │ │ spatial_ops      │  │ │
│  │ │ - getcaps   │ │ - put/get    │ │ - aggregate      │  │ │
│  │ │ - get_feat  │ │ - sidecar    │ │ - filter_attr    │  │ │
│  │ │ - ogc_filter│ │ - lineage    │ │ (geopandas)      │  │ │
│  │ └─────────────┘ └──────────────┘ └──────────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                        │
                        ▼
              ┌──────────────────────┐
              │ data/results/        │
              │ ├── result_001.geojson│
              │ ├── result_001.json  │   (sidecar metadata)
              │ └── ...              │
              └──────────────────────┘

External : api.accept.montreal.ca (WFS) + Ollama (localhost:11434)
```

**Composants :**

- **Frontend Next.js** : carte MapLibre, dessin via terra-draw, chat CopilotKit, panneau de datasets
- **Backend FastAPI** : agent LangGraph + 3 services (`wfs_client`, `result_store`, `spatial_ops`)
- **Store sur disque** : `data/results/` avec un GeoJSON + un sidecar JSON par dataset

## Backend : agent LangGraph

### Modèle d'agent

Agent **ReAct** créé via `create_react_agent` de `langgraph.prebuilt`. Pas de graphe custom au MVP — un agent ReAct avec une bonne palette d'outils suffit. Évolution possible vers un graphe custom plus tard si on veut des étapes contraintes (ex: validation systématique avant écriture sur disque).

LLM : `langchain_ollama.ChatOllama(model=settings.OLLAMA_MODEL, base_url=settings.OLLAMA_BASE_URL)`.

### État partagé (CopilotKit `useCoAgent`)

```python
class AgentState(TypedDict):
    datasets: list[DatasetMeta]      # tous les résultats (sans geom)
    current_drawing: GeoJSON | None  # polygone dessiné par l'utilisateur
    active_layers: list[str]         # IDs de datasets affichés sur la carte
    last_error: str | None
```

`DatasetMeta` (jamais la géométrie, juste les métadonnées) :

```python
class DatasetMeta(BaseModel):
    id: str                          # "result_001"
    alias: str | None                # nommé par l'agent ("parcs_dans_polygone")
    source: SourceInfo               # type wfs ou derived
    feature_count: int
    bbox: tuple[float, float, float, float]
    attribute_schema: dict[str, str] # {"name": "string", "area": "number"}
    lineage: LineageInfo
    created_at: datetime
    size_bytes: int
```

### Outils exposés à l'agent

| Tool | Purpose | Inputs | Output |
|---|---|---|---|
| `list_wfs_layers` | Découverte WFS via GetCapabilities (cached) | — | liste de `{name, title, abstract, attribute_schema}` |
| `select_features` | Charge des features depuis le WFS via filtre OGC | `layer`, `geometry_filter` (polygon depuis drawing OU dataset_id), `spatial_predicate` (intersects/within/contains/dwithin), `attribute_filter` (optionnel), `alias` | nouveau `dataset_id` + meta |
| `aggregate` | Stats sur un dataset | `dataset_id`, `op` (count/sum/mean/min/max), `attribute`, `group_by` (optionnel) | résultat textuel + (optionnel) nouveau dataset si group_by |
| `filter_attributes` | Filtre attributaire local | `dataset_id`, `predicate`, `alias` | nouveau `dataset_id` |
| `show_on_map` / `hide_on_map` | Toggle de visibilité (modifie `active_layers`) | `dataset_id` | — |
| `describe_dataset` | Récupère les meta d'un dataset (l'agent peut s'y référer sans relire le fichier) | `dataset_id` ou `alias` | meta complet |
| `list_datasets` | Liste tous les datasets disponibles (alias + ID + count) | — | liste de `DatasetMeta` allégés |

`select_features` accepte soit le polygone courant (`current_drawing`), soit un `dataset_id` source pour le chaînage. Dans le second cas, on prend la **bbox unionnée** par défaut (rapide, filtre côté serveur), avec option `use_geometry: true` pour utiliser la géométrie complète (filtre Intersects précis, mais payload plus gros — cap de taille du body XML).

### Garde-fous

- `MAX_FEATURES_PER_QUERY` (par défaut 5000) — si dépassé, erreur claire suggérant raffinement
- `MAX_FILTER_GEOMETRY_VERTICES` (par défaut 1000) — au-delà, simplification automatique avec `shapely.simplify` ou bascule sur bbox
- Timeout HTTP WFS : 30s

## Frontend : Next.js + CopilotKit + MapLibre

### Structure

```
frontend/
├── app/
│   ├── layout.tsx          # <CopilotKit runtimeUrl="/api/copilotkit"> wrapper
│   ├── page.tsx            # page principale
│   └── api/
│       └── copilotkit/
│           └── route.ts    # adapter qui forward au FastAPI LangGraph
├── components/
│   ├── Map/
│   │   ├── MapView.tsx     # MapLibre + style fond-de-carte
│   │   ├── DrawTool.tsx    # terra-draw (polygon mode)
│   │   └── DatasetLayer.tsx# rend un dataset comme source GeoJSON
│   ├── DatasetPanel.tsx    # bottom panel
│   └── AgentStateRenderers/
│       ├── DatasetCard.tsx
│       └── AnalysisProgress.tsx
├── lib/
│   ├── basemap.ts
│   └── types.ts            # zod schemas partagés
└── package.json
```

### Synchronisation d'état

Hook `useCoAgent<AgentState>("geo-agent")` donne accès en temps réel à :

- `datasets` → alimente le panneau du bas et les couches affichables
- `current_drawing` → écrit par `DrawTool` quand l'utilisateur termine un polygone, lu par l'agent
- `active_layers` → contrôle quelles couches sont visibles sur la carte
- `last_error` → affiché en toast

### Flow de dessin

1. Utilisateur clique "Dessiner zone" dans le panneau ou dans le chat → `terra-draw` passe en mode polygon
2. À la fin du dessin → `setState({ current_drawing: polygon })`
3. Le chat reflète "Polygone prêt" comme contexte visuel
4. Utilisateur tape sa demande → l'agent voit `current_drawing` dans son état et l'utilise

### Rendu de couches sur la carte

Chaque `dataset_id` dans `active_layers` est une source GeoJSON MapLibre. Chargement via une route Next.js `/api/datasets/[id]` qui proxie le backend FastAPI `/datasets/{id}/geojson`. Les chemins fichiers ne sortent jamais du backend.

### Generative UI

- Pendant l'exécution de `select_features` : `AnalysisProgress` (spinner + "Filtre OGC : Within(polygon) sur montreal:parcs")
- Une fois terminé : `DatasetCard` avec count, bbox, bouton "Afficher sur la carte"

### Bibliothèques

- `maplibre-gl` (carte)
- `terra-draw` + `terra-draw-maplibre-gl-adapter` (dessin)
- `@copilotkit/react-core` + `@copilotkit/react-ui`
- `zod` (validation schémas partagés)

## Intégration WFS et filtres OGC

### Découverte (`list_wfs_layers`)

Au premier appel, GET `?service=WFS&version=2.0.0&request=GetCapabilities`, parsing des `FeatureType`, cache mémoire (TTL 1h) + cache disque (`data/wfs_capabilities_cache.json`).

Pour chaque couche, on extrait `name`, `title`, `abstract`, `default_crs`, `bbox`. L'`attribute_schema` est récupéré via `DescribeFeatureType` à la première utilisation effective de la couche (lazy).

### Construction du filtre OGC (WFS 2.0, FES 2.0)

Le client construit un filtre XML structuré avec `lxml` et namespaces explicites — jamais par concaténation de chaînes (sécurité + correction).

```python
def build_filter(
    spatial: SpatialFilter | None,    # {predicate, geometry, geom_property}
    attributes: AttributeFilter | None # {property, op, value}
) -> str:
    # Combine via <fes:And> si les deux présents
    # Génère <fes:Intersects>, <fes:Within>, <fes:BBOX>, <fes:DWithin>
    # GML 3.2 pour les géométries (gml:Polygon, gml:Envelope)
```

### Requête type

`POST /wfs?service=WFS&version=2.0.0&request=GetFeature&outputFormat=application/json` avec body XML :

```xml
<wfs:GetFeature ...>
  <wfs:Query typeNames="montreal:chaussees" srsName="EPSG:4326">
    <fes:Filter>
      <fes:And>
        <fes:Intersects>
          <fes:ValueReference>geom</fes:ValueReference>
          <gml:Polygon>...</gml:Polygon>
        </fes:Intersects>
        <fes:PropertyIsGreaterThan>
          <fes:ValueReference>longueur_m</fes:ValueReference>
          <fes:Literal>100</fes:Literal>
        </fes:PropertyIsGreaterThan>
      </fes:And>
    </fes:Filter>
  </wfs:Query>
</wfs:GetFeature>
```

### Découverte du `geom_property`

Le nom de la propriété géométrique varie par couche (`geom`, `the_geom`, `wkb_geometry`...). On le récupère via `DescribeFeatureType` à la première utilisation et on le cache avec le schéma d'attributs.

### Garde-fous

- `count` (équivalent `maxFeatures` en WFS 2.0) toujours envoyé = `MAX_FEATURES_PER_QUERY + 1`. Si la réponse renvoie cette taille, on rejette et on lève `TooManyFeaturesError`.
- Si la géométrie de filtre dépasse `MAX_FILTER_GEOMETRY_VERTICES`, simplification ou bascule bbox.

### Fallback WFS 1.0.0/1.1.0

Si le serveur ne supporte pas 2.0.0 (GetCapabilities échoue), bascule vers `version=1.1.0` (FES 1.1, syntaxe légèrement différente — `PropertyName` au lieu de `ValueReference`). La couche d'abstraction choisit la version au démarrage.

## Store de résultats

### Layout disque

```
data/
├── results/
│   ├── result_001.geojson       # FeatureCollection (les vraies géométries)
│   ├── result_001.json          # sidecar metadata
│   ├── result_001.filter.xml    # filtre OGC qui a produit ce résultat (debug)
│   └── ...
├── wfs_capabilities_cache.json
└── sessions/
    └── current.json             # snapshot AgentState (datasets[], aliases) au shutdown
```

### Sidecar metadata

```json
{
  "id": "result_001",
  "alias": "parcs_dans_polygone",
  "source": {
    "type": "wfs",
    "layer": "montreal:parcs",
    "filter_summary": "Within(current_drawing)",
    "request_url": "...",
    "filter_xml_path": "result_001.filter.xml"
  },
  "feature_count": 47,
  "bbox": [-73.7, 45.4, -73.5, 45.6],
  "attribute_schema": {"name": "string", "area_m2": "number", "type": "string"},
  "lineage": {
    "parent_ids": [],
    "operation": "select_features",
    "params": {"layer": "montreal:parcs", "spatial_predicate": "within"}
  },
  "created_at": "2026-05-09T14:32:00Z",
  "size_bytes": 124530
}
```

### Interface

```python
class ResultStore(Protocol):
    def put(self, geojson: dict, meta_partial: dict) -> str  # returns id
    def get_geojson(self, id: str) -> dict
    def get_meta(self, id: str) -> DatasetMeta
    def list(self) -> list[DatasetMeta]
    def delete(self, id: str) -> None
    def update_alias(self, id: str, alias: str) -> None
```

Implémentation MVP : `FileSystemResultStore`. Plus tard, swap pour `S3ResultStore` ou `DuckDBResultStore` sans toucher à l'agent.

### Cycle de vie

- IDs alloués séquentiellement (`result_NNN`) avec compteur persistant dans `sessions/current.json`
- Au démarrage : on lit `sessions/current.json` pour reconstruire la liste des datasets dans l'état de l'agent
- L'agent commence chaque conversation avec un contexte propre — les datasets restent disponibles via `describe_dataset` ou `list_datasets`
- Pas de cleanup automatique. Commande explicite `clear_session` (CLI ou bouton UI) supprime `data/results/*` et reset le compteur.

## Gestion d'erreurs

| Source | Type | Comportement |
|---|---|---|
| WFS HTTP 4xx/5xx | Réseau / serveur indispo | Tool retourne erreur structurée → l'agent voit le message et peut réessayer ou abandonner ; toast côté UI |
| WFS renvoie `>MAX_FEATURES_PER_QUERY` | Sur-collecte | `TooManyFeaturesError` avec suggestion ; l'agent réagit en raffinant ou en demandant à l'utilisateur |
| Filtre OGC invalide | Bug code | Erreur structurée + log détaillé ; pas de retry |
| Layer inconnu / typo | Hallucination agent | Tool renvoie la liste des couches valides ; l'agent recommence |
| `current_drawing` requis mais absent | UX | Erreur métier ; l'agent demande à l'utilisateur de dessiner |
| Ollama timeout / down | Infra locale | Erreur dans le chat avec indication "Vérifie qu'`ollama serve` tourne" |
| GeoJSON corrompu sur disque | Bug interne | Log + erreur claire ; pas de tentative de récupération |

**Principe** : chaque outil renvoie soit un succès structuré, soit un `ToolError` avec `code` + `message` + `suggestion`. L'agent voit ces erreurs comme des messages outils normaux et peut adapter sa stratégie. On ne masque jamais les erreurs.

## Tests

### Backend (pytest)

- **`wfs_client` / `ogc_filter`** : tests unitaires de la construction des filtres OGC (parsing du XML produit, vérification structure FES 2.0). Tests d'intégration avec fichiers de réponse WFS capturés en fixture. Un test e2e marqué `@pytest.mark.live` qui frappe le vrai WFS Montréal — exécuté manuellement.
- **`spatial_ops`** : tests purs avec FeatureCollections fixtures (count/sum/mean/group_by + edge cases : 0 features, attributs nuls, types mixtes).
- **`result_store`** : tests sur `tmp_path`. Round-trip put/get, lineage, listing, alias.
- **Outils LangGraph** : tests de chaque tool en isolation. Pas de test du LLM lui-même. Un test e2e `@live` qui exécute un scénario complet avec gemma4:e4b — pour détecter régressions de prompt/tool schema.

### Frontend (Vitest + Playwright)

- **Composants** : tests Vitest pour `DatasetPanel`, `DatasetCard`, hooks (`useCoAgent` mocké).
- **`DrawTool`** : test que terminer un polygone met bien à jour `current_drawing` dans l'état.
- **E2E (Playwright)** : scénario heureux end-to-end avec backend mocké : utilisateur dessine → tape une question → reçoit un dataset → l'affiche sur la carte.

### Approche TDD

- Logique pure et déterministe (`wfs_client`, `ogc_filter`, `spatial_ops`, `result_store`) : TDD strict (rouge → impl → vert)
- Composants UI et intégration LangGraph : tests rédigés après une première version exploratoire

## Structure du repo et mise en route

```
geo-agent/
├── README.md
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── geo_agent/
│   │   ├── main.py
│   │   ├── agent/
│   │   │   ├── graph.py
│   │   │   ├── prompts.py
│   │   │   └── tools/
│   │   │       ├── list_wfs_layers.py
│   │   │       ├── select_features.py
│   │   │       ├── aggregate.py
│   │   │       ├── filter_attributes.py
│   │   │       ├── show_on_map.py
│   │   │       ├── describe_dataset.py
│   │   │       └── list_datasets.py
│   │   ├── services/
│   │   │   ├── wfs_client.py
│   │   │   ├── ogc_filter.py
│   │   │   ├── result_store.py
│   │   │   └── spatial_ops.py
│   │   ├── routes/
│   │   │   ├── copilotkit.py
│   │   │   └── datasets.py
│   │   └── config.py
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── fixtures/
├── frontend/
│   ├── package.json
│   ├── next.config.ts
│   ├── tsconfig.json
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── tests/
│       ├── unit/
│       └── e2e/
├── data/                    # gitignored
│   ├── results/
│   ├── sessions/
│   └── wfs_capabilities_cache.json
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-05-09-geo-agent-design.md
```

### Stack & versions cibles

- **Backend** : Python 3.12+, FastAPI, LangGraph, `langchain-ollama`, `geopandas`, `shapely`, `lxml`, `httpx`, `pydantic-settings`, `pytest`
- **Frontend** : Next.js 15 (App Router), React 19, TypeScript, `maplibre-gl`, `terra-draw` + adapter MapLibre, `@copilotkit/react-core` + `@copilotkit/react-ui`, `zod`, Vitest, Playwright
- **Modèle** : `gemma4:e4b` via Ollama (configurable via `OLLAMA_MODEL`)

### Mise en route locale

```bash
# 1. Ollama (s'il ne tourne pas déjà)
ollama serve

# 2. Backend
cd backend && uv sync && uv run uvicorn geo_agent.main:app --reload

# 3. Frontend
cd frontend && npm install && npm run dev   # http://localhost:3000
```

### Variables d'environnement (`.env`)

```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:e4b
WFS_BASE_URL=https://api.accept.montreal.ca/api/it-platforms/geomatic/wfs-maps/montreal/ows
BASEMAP_STYLE_URL=https://api.accept.montreal.ca/api/it-platforms/geomatic/map-assets/v1/styles/fond-de-carte
DATA_DIR=./data
MAX_FEATURES_PER_QUERY=5000
MAX_FILTER_GEOMETRY_VERTICES=1000
WFS_HTTP_TIMEOUT_SECONDS=30
```

## Critères de succès du MVP

1. Démarrer l'app → carte avec fond Montréal s'affiche
2. Demander à l'agent "quelles couches sont disponibles ?" → réponse avec liste depuis GetCapabilities
3. Dessiner un polygone, taper "trouve les chaussées dans cette zone" → l'agent appelle `select_features` avec filtre OGC `Within`, dataset créé, affichable sur la carte
4. Demander "compte-les par type" → l'agent appelle `aggregate` avec `group_by`
5. Demander "garde celles qui font plus de 200m, puis trouve les bâtiments à moins de 50m" → chaînage : `filter_attributes` → `select_features` avec `dataset_id` parent + `dwithin`
6. Le panneau de datasets liste tous les résultats avec leur lineage
7. Aucun GeoJSON dans le contexte de l'agent — uniquement IDs et métadonnées
