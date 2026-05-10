# Frontend widgets — design

**Date:** 2026-05-10
**Scope:** Three specialised widgets that render structured data inside the geo-agent frontend.

## 1. Goal

Replace ad-hoc text dumps and minimal placeholder cards with three rich, focused widgets that let the user inspect:

1. **Dataset metadata** — id, alias, feature count, source layer, size, lineage
2. **Feature schema** — attribute names, types, sample values; on-demand per-attribute statistics
3. **A single feature** — properties, geometry summary, with the feature visually highlighted on the map

The first two render inline in the CopilotKit chat sidebar. The third is map-driven (popup → drawer) and lives outside the chat.

## 2. User-facing surfaces

| Widget | Location | Trigger |
|---|---|---|
| `MetadataWidget` | Inline in chat | Agent calls `describe_dataset` (or any tool whose result is a `DatasetMeta`) |
| `SchemaWidget` | Inline in chat | "Voir le schéma" button on `MetadataWidget` (always reached via composition — no direct tool trigger) |
| `FeaturePopup` | MapLibre popup anchored to the clicked feature | User clicks a rendered feature on the map |
| `FeatureDrawer` | Right-side panel (~300 px) over the map | "Détails" button in `FeaturePopup` |
| `HighlightLayer` | MapLibre layers (always mounted, empty by default) | A `FeatureDrawer` is open |

The popup is intentionally minimal (title + 2–3 stats + "Détails" link). The drawer carries the full property table, geometry summary, and actions.

## 3. Architecture

### 3.1 Chat-resident widgets piggyback on existing tools

Both `MetadataWidget` and `SchemaWidget` are rendered through CopilotKit's per-tool render hook:

```ts
useCopilotAction({
  name: "describe_dataset",
  render: ({ args, result, status }) => (
    <MetadataWidget data={result} datasetId={args.id_or_alias} status={status} />
  ),
});
```

`describe_dataset` already returns the full `DatasetMeta` (id, alias, source, feature_count, bbox, attribute_schema, lineage, created_at, size_bytes), so no backend changes are needed for the two chat widgets to render. The same hook covers the `select_features` and `filter_attributes` tools, which return a similar shape — they get a `MetadataWidget` for their newly-created dataset.

The widgets render in addition to the LLM's narrative text; CopilotKit's default tool-result text is replaced by the widget for the registered tool names.

### 3.2 Widget composition: schema-from-metadata

`MetadataWidget` carries a "Voir le schéma" button. Clicking it does **not** call the agent; instead, the widget toggles its own internal view to schema mode and renders `SchemaWidget` inline using the `attribute_schema` field already present in the same `DatasetMeta` payload. This keeps composition local and avoids an LLM round-trip for a deterministic action.

`SchemaWidget` makes two kinds of network calls of its own:

1. **First mount:** `GET /api/datasets/[id]` to read the first feature and populate the "Exemple" column. The result is cached in component state.
2. **On row expand:** `GET /api/datasets/[id]/attributes/[name]/stats` for per-attribute statistics; see §3.4.

### 3.3 Map-driven widgets

`FeaturePopup` and `FeatureDrawer` are React components rendered inside the existing `MapView`/`GeoPage` tree, not via CopilotKit. Selection state lives in a small React context provided by `GeoPage`:

```ts
type SelectedFeature = {
  datasetId: string;
  index: number;     // index into the dataset's GeoJSON features array
  feature: GeoJSON.Feature;
} | null;
```

`MapView` registers a `map.on('click', layerId)` handler for each active dataset's three layers (fill, line, circle). The handler resolves the feature back to its index by matching the rendered GeoJSON feature against the cached source data, then sets the selection.

When `selectedFeature !== null`:
- `FeaturePopup` mounts as a MapLibre popup at the click coordinates
- `FeatureDrawer` is hidden until the user clicks "Détails"
- `HighlightLayer` mirrors `feature.geometry` into a dedicated MapLibre source

When the drawer or popup is closed, selection clears and the highlight source is emptied.

### 3.4 Backend: one new endpoint

Per-attribute statistics are computed server-side to avoid shipping multi-MB GeoJSONs to the browser for one stat. Add to `backend/geo_agent/routes/datasets.py`:

```
GET /datasets/{id}/attributes/{name}/stats
```

Response shape:

```json
{
  "attribute": "longueur_m",
  "type": "number",
  "non_null_count": 1245,
  "null_count": 2,
  "distinct_count": 987,
  "min": 3.1,
  "max": 412.7,
  "top_values": [{ "value": "Asphalte", "count": 1012 }, ...]   // strings only
}
```

Computed by reading the dataset's GeoJSON (already on disk via `result_store.get_geojson(id)`), iterating `feature.properties[name]`, and summarising. No persistence; computed on each call. The Next.js side adds a thin proxy at `/api/datasets/[id]/attributes/[name]/stats`.

`SchemaWidget` calls this endpoint lazily on the first expand of an attribute and caches the result in component state for the lifetime of the widget instance.

### 3.5 Highlight mechanism

A single `HighlightLayer` component mounts three MapLibre layers backed by a single source called `highlight-source`:

| Layer id | Type | Filter | Paint |
|---|---|---|---|
| `highlight-fill` | fill | Polygon | `fill-color: #fbbf24, fill-opacity: 0.4` |
| `highlight-line` | line | LineString | `line-color: #fbbf24, line-width: 5, line-opacity: 0.95` |
| `highlight-circle` | circle | Point | `circle-color: #fbbf24, circle-radius: 12, circle-stroke-width: 3, circle-stroke-color: #92400e` |

The source is created empty at mount. When `selectedFeature` changes, the source's data is set to a single-feature `FeatureCollection`. When `selectedFeature` clears, the source is set to an empty `FeatureCollection`.

Layers are added to the map *above* all `ds-*` dataset layers so the highlight is never occluded. No `feature-state` is used — this avoids the question of stable WFS feature IDs entirely.

The "atténuation des autres features" effect is achieved by reading the current `selectedFeature` in `DatasetLayer` and lowering the opacity of that dataset's layers (e.g., `fill-opacity: 0.1`, `line-opacity: 0.2`) when something is selected — the highlight source draws the chosen feature on top with full saturation. The other (non-selected-dataset) layers stay untouched.

A pulse halo is added via a CSS-driven `@keyframes` animation on the `highlight-line`'s `line-blur`/`line-width` if MapLibre supports it through interpolate; otherwise a simpler static halo is acceptable.

## 4. Component breakdown

### 4.1 `MetadataWidget`

- **Props:** `{ data: DatasetMeta, datasetId: string, status: "executing" | "complete" }`
- **Layout:** badge + name + id, three stat tiles (features count, source layer, size), lineage breadcrumb (parent ids → operation → current), three action buttons:
  - **Voir le schéma** → toggle internal view to `SchemaWidget`
  - **Afficher sur la carte** → calls `setActiveLayers([...current, datasetId])` via `useCoAgent` setState
  - **Cadrer la carte** → reads `bbox` from the meta and calls `map.fitBounds(bbox)` via the map context
- **Loading state:** when `status === "executing"`, render a skeletonised version with placeholders.

### 4.2 `SchemaWidget`

- **Props:** `{ data: DatasetMeta, datasetId: string }`
- **Layout:** badge + name + attribute count, then a 3-column table (Attribut / Type / Exemple). Type chip colours: `number` blue, `string` green, `boolean` amber. Sample value is taken from the first feature of the dataset's GeoJSON (lazily fetched once, cached).
- **Expand mode:** clicking a row toggles a sub-section beneath that row showing the per-attribute stats fetched from `/api/datasets/{id}/attributes/{name}/stats`. Loading state shows a small spinner; once loaded, stats are displayed and cached for the widget's lifetime. Multiple rows can be expanded at once.
- **No pagination.** Vertical scroll inside the widget is acceptable.

### 4.3 `FeaturePopup`

- **Mount:** instantiated as a `new maplibregl.Popup()` at the click coordinates, with React content via `createPortal`.
- **Content:** title (best-effort guess: first string property whose name matches `nom*`, `name`, `title`, else `id_*`, else "Feature #N"), 2–3 secondary stats (best-effort: numeric properties), and a "Détails" link that opens the `FeatureDrawer`.
- **Dismissal:** clicking elsewhere on the map closes the popup *and* clears the selection (which removes the highlight). Closing only the popup while keeping the drawer open is not supported in v1.

### 4.4 `FeatureDrawer`

- **Mount:** a fixed React component, ~300 px wide, anchored to the right edge over the map. Hidden when `!selectedFeature` or when the user has not clicked "Détails".
- **Layout:** header (badge "FEATURE", title, dataset id + feature index, close ×), Properties table (all properties, monospace keys, right-aligned values), Geometry section (type, vertex count), two action buttons:
  - **Cadrer la carte sur la feature** → computes the feature's bbox and calls `map.fitBounds(...)`
  - **Demander à l'agent…** → opens the chat sidebar (if collapsed) and pre-fills the input with `Au sujet de la feature #{index} du dataset {id_or_alias} (« {title} »), `; the cursor lands at the end of the prompt for the user to finish.
- **Highlight bandeau:** **omitted.** (Per design discussion — the highlight on the map is self-evident.)
- **Close:** × button clears `selectedFeature`, which unmounts the drawer, the popup, and empties the highlight source.

### 4.5 `HighlightLayer`

- **Props:** none. Reads `selectedFeature` from context.
- **Lifecycle:** mounts once at `MapView` level. On `selectedFeature` change, calls `setData` on `highlight-source`. On unmount, removes layers and source.

## 5. Data flow

```
User clicks describe_dataset args in agent reasoning
  → backend `describe_dataset` returns DatasetMeta
    → CopilotKit streams tool result
      → `useCopilotAction({ name: "describe_dataset", render })` matches
        → MetadataWidget renders inline in chat
          → user clicks "Voir le schéma"
            → MetadataWidget toggles to SchemaWidget (no network)
              → user expands `longueur_m` row
                → SchemaWidget GET /api/datasets/result_002/attributes/longueur_m/stats
                  → Stats subrow renders, cached locally

User clicks a road segment on the map
  → MapView click handler resolves to (datasetId, index, feature)
    → SelectedFeatureContext.set(...)
      → FeaturePopup mounts at click point
      → HighlightLayer source updated → road draws in gold
      → DatasetLayer (the parent dataset's) lowers its own opacity
        → user clicks "Détails" in the popup
          → FeatureDrawer mounts
            → user clicks "Demander à l'agent…"
              → CopilotSidebar opens with prefilled input
```

## 6. File changes

### New
- `frontend/components/Widgets/MetadataWidget.tsx`
- `frontend/components/Widgets/SchemaWidget.tsx`
- `frontend/components/Widgets/AttributeStatsRow.tsx` (small helper used inside SchemaWidget)
- `frontend/components/Map/FeaturePopup.tsx`
- `frontend/components/Map/FeatureDrawer.tsx`
- `frontend/components/Map/HighlightLayer.tsx`
- `frontend/lib/selectedFeature.tsx` (React context for the selected feature)
- `frontend/app/api/datasets/[id]/attributes/[name]/stats/route.ts` (proxy)
- `backend/geo_agent/routes/datasets.py` — add `GET /datasets/{id}/attributes/{name}/stats` route
- `backend/geo_agent/services/attribute_stats.py` — small module that takes a GeoJSON + attribute name and returns the stats dict

### Modified
- `frontend/components/GeoPage.tsx` — wrap subtree in `SelectedFeatureProvider`, register the three `useCopilotAction` widget renderers, mount `FeatureDrawer`
- `frontend/components/Map/MapView.tsx` — register click handlers for active dataset layers; mount `HighlightLayer` and `FeaturePopup`
- `frontend/components/Map/DatasetLayer.tsx` — read `selectedFeature`; when a feature in *this* dataset is selected, dim the layers' opacity
- `frontend/components/AgentStateRenderers/DatasetCard.tsx` — **delete** (replaced by `MetadataWidget`)

## 7. Testing

- **Unit (Vitest):**
  - `MetadataWidget` renders all three stat tiles, lineage breadcrumb, three buttons; clicking "Voir le schéma" switches to schema mode
  - `SchemaWidget` renders the expected number of rows; clicking a row triggers a fetch and displays the stats
  - `attribute_stats.py` returns correct min/max/distinct/null counts on synthetic GeoJSONs (number, string, boolean, mixed)
- **Component-with-map (Vitest + jsdom):**
  - `HighlightLayer` adds and removes its source/layers in response to context changes
  - `FeaturePopup` mounts/unmounts on selection change
- **E2E (Playwright):**
  - Draw a polygon → ask the agent to find streets → verify the agent's response includes a `MetadataWidget` with the expected feature count
  - Click "Voir le schéma" → table renders → expand an attribute row → stats appear
  - Click a feature on the map → popup appears → click "Détails" → drawer opens → highlight is visible (assert via screenshot diff or by checking the highlight source has a feature)

## 8. Out of scope (v1)

- Editing properties (read-only)
- Pagination of schema (vertical scroll accepted)
- Widgets for `aggregate`, `list_wfs_layers`, `list_datasets` (only the three asked-for cases)
- Multi-select of features
- Cross-dataset filtering driven from the drawer
- Persisting selection across page reloads
- Animating the highlight halo if MapLibre's interpolate doesn't make it trivial — accept a static halo as fallback

## 9. Notable design choices

1. **No new LangGraph tools.** The widgets piggyback on the existing tools' return shapes; the LLM doesn't need a new vocabulary.
2. **Composition is local.** "Voir le schéma" doesn't go back to the agent — it toggles the widget's internal view using data already in the payload.
3. **Highlight is a separate source, not `feature-state`.** This sidesteps the question of stable feature IDs across WFS calls and keeps the highlight trivially clearable.
4. **The popup is the entry point, the drawer is the workspace.** Two surfaces, one selection state, no duplication.
5. **Stats are computed server-side, on demand.** The dataset can be multi-MB; we ship one summary, not the whole file, when the user wants stats on one column.
