# Tools revision — design

**Date:** 2026-05-11
**Scope:** Reorganize the geo-agent's tools into three explicit families (WFS server / local datasets / UI) and add the missing capabilities — local geometry operations between and over datasets, and agent-driven inspection views in the chat.

## 1. Goal

The agent works, but the tool surface is uneven: it can only filter and aggregate locally (no overlay, buffer, clip, spatial join), it has no way to read a WFS layer's attribute names before filtering on them, and the only way it can "show" something is `show_on_map`. This redesign:

1. Splits `agent/tools/` into three subpackages — `wfs/`, `datasets/`, `ui/` — so both the code and the system prompt mirror one mental model.
2. Adds `describe_wfs_layer` (WFS family).
3. Adds `spatial_overlay`, `transform_geometry`, `spatial_join` (datasets family).
4. Adds `inspect_dataset` (UI family) — pushes a schema / feature / feature-list view into the chat.
5. Rewrites the `# Tool catalog` section of `SYSTEM_PROMPT` to mirror the three families, with a concrete JSON example per new tool.

Tool count goes from 8 to 13. Verbs are consolidated (one `spatial_overlay` with an `op` discriminator rather than four separate tools, etc.) to keep tool-calling reliable on the local LLM (Qwen2.5 7B by default).

## 2. Tool catalog (13 tools)

### 2.1 WFS server tools — remote, query Montreal's geomatics server

| Tool | Signature | Status |
|---|---|---|
| `list_wfs_layers` | `() -> list[{name, title, abstract}]` | unchanged, relocated to `tools/wfs/list_layers.py` |
| `describe_wfs_layer` | `(layer: str) -> {layer, geometry_type, default_crs, attributes: [{name, type}]}` | **new** — `tools/wfs/describe_layer.py` |
| `select_features` | `(layer, geometry_source, spatial_predicate, attribute_filter?, distance_meters?, alias?) -> Command` | unchanged, relocated to `tools/wfs/select_features.py` |

`describe_wfs_layer` wraps `services.wfs.describe_feature_type(layer)` (already cached permanently) and returns the attribute list + geometry property type + CRS. It does not return any features. It exists so the agent can learn attribute names before issuing a `select_features` with an `attribute_filter` — the WFS-side parallel of `describe_dataset` before `filter_attributes`. On an unknown layer it returns a `ToolError(code="layer_not_found", suggestion=<list of layer names>)`.

### 2.2 Local dataset tools — in-memory, operate on datasets already produced

| Tool | Signature | Status |
|---|---|---|
| `filter_attributes` | `(dataset_id, predicate, alias?) -> Command` | unchanged, relocated to `tools/datasets/filter_attributes.py` |
| `aggregate` | `(dataset_id, op, attribute?, group_by?) -> dict \| Command` | unchanged, relocated to `tools/datasets/aggregate.py` |
| `spatial_overlay` | `(left_id, right_id, op, alias?) -> Command` | **new** — `tools/datasets/spatial_overlay.py` |
| `transform_geometry` | `(dataset_id, op, distance_meters?, tolerance?, by?, alias?) -> Command` | **new** — `tools/datasets/transform_geometry.py` |
| `spatial_join` | `(left_id, right_id, predicate, alias?) -> Command` | **new** — `tools/datasets/spatial_join.py` |
| `describe_dataset` | `(id_or_alias) -> dict \| Command` | unchanged, relocated to `tools/datasets/describe_dataset.py` |
| `list_datasets` | `() -> list[dict]` | unchanged, relocated to `tools/datasets/list_datasets.py` |

**`spatial_overlay`** — `op` is one of `intersection | union | difference | clip`:

- `intersection` — features of `left` clipped to `right`, keeping `left`'s attributes (the most common one: "the streets that cross this park").
- `union` — geometric union of both layers' features (attributes from both, null-filled where absent).
- `difference` — `left` minus the parts that overlap `right` (keeps `left`'s attributes).
- `clip` — like `intersection` but explicitly framed as "trim `left` to the boundary of `right`"; semantically the same operation as `intersection`, exposed as a separate `op` value because the LLM (and the user) talk about it differently. Implemented by the same code path.

Lineage: `parent_ids = [left_id, right_id]`, `operation = "spatial_overlay"`, `params = {"op": <op>}`.

**`transform_geometry`** — `op` is one of `buffer | centroid | simplify | dissolve`:

- `buffer` — requires `distance_meters` (a positive number). Reproject to EPSG:32188 (NAD83 / MTM zone 8 — Montreal's metric reference), `geom.buffer(distance_meters)`, reproject back to EPSG:4326. Attributes preserved.
- `centroid` — replace each feature's geometry with its centroid (Point). Attributes preserved.
- `simplify` — requires `tolerance` (in degrees, since the data is EPSG:4326; document the unit and give an example value like `0.0001`). Douglas–Peucker. Attributes preserved.
- `dissolve` — merge features. If `by` (an attribute name) is given, merge per distinct value of that attribute and keep that attribute; otherwise merge everything into one feature with no attributes.

Lineage: `parent_ids = [dataset_id]`, `operation = "transform_geometry"`, `params = {"op": <op>, ...the relevant param}`.

Validation: `buffer` without `distance_meters` → `ToolError(code="bad_input", suggestion="buffer requires distance_meters")`. `simplify` without `tolerance` → same pattern. `dissolve` with a `by` attribute not in the dataset's schema → `ToolError(code="bad_input")`.

**`spatial_join`** — attach `right`'s attributes to each feature of `left` based on a spatial `predicate` (`intersects | within | contains`). Geometry stays `left`'s. When a `left` feature matches multiple `right` features, the first match wins (document this; a `how` parameter for one-to-many is out of scope for v1). When it matches none, the `right` attributes are null. Attribute-name collisions are resolved by suffixing the `right` columns with `_r`.

Lineage: `parent_ids = [left_id, right_id]`, `operation = "spatial_join"`, `params = {"predicate": <predicate>}`.

All three producing tools:
- read inputs via `services.store.get_geojson(...)` and emit a `dataset_not_found` `ToolError` (with `suggestion` listing valid ids) on a miss — same pattern as `select_features` / `filter_attributes` today;
- write the result via `services.store.put(out, {...metadata...})` and return `dataset_created_command(meta_lite, tool_result={...}, state, tool_call_id)` — same pattern as today;
- if the result is empty (zero features), still persist it but include a hint, and emit no error by default — except `spatial_overlay`/`spatial_join`, which return `ToolError(code="empty_result", suggestion="left and right do not overlap; check the inputs or the predicate")` because an empty overlay is almost always a mistake.

### 2.3 UI tools — surface a view to the user

| Tool | Signature | Status |
|---|---|---|
| `show_on_map` | `(dataset_id, state, tool_call_id) -> Command` | unchanged, relocated to `tools/ui/show_on_map.py` |
| `hide_on_map` | `(dataset_id, state, tool_call_id) -> Command` | unchanged, in the same file |
| `inspect_dataset` | `(dataset_id, view, feature_index?) -> dict \| Command` | **new** — `tools/ui/inspect_dataset.py` |

**`inspect_dataset`** — `view` is one of `schema | features | feature`:

- `schema` — returns `{view: "schema", dataset_id, alias, attribute_schema, sample: {<attr>: <value>, ...}}` where `sample` is taken from the first feature's properties. Renders `SchemaWidget` inline.
- `features` — returns `{view: "features", dataset_id, alias, total, features: [{index, properties, geometry_type}, ...]}` capped at the first 50 features. Renders `FeatureListWidget`.
- `feature` — requires `feature_index` (int). Returns `{view: "feature", dataset_id, alias, index, properties, geometry_type, vertex_count}`. Renders `FeatureWidget`. Out-of-range index → `ToolError(code="bad_input", suggestion="dataset has N features; index must be 0..N-1")`.

The tool reads the dataset's GeoJSON via `services.store.get_geojson(dataset_id)`, **strips all coordinates** (keeps only `geometry_type` and, for `feature`, `vertex_count`), and returns the compact echo above. That echo is both what the LLM sees in the `ToolMessage` and what the CopilotKit renderer receives as `result`. The "agent never sees GeoJSON" rule stays true in the geometric sense — the agent sees feature *properties*, never coordinates. Unknown `dataset_id` → `dataset_not_found` `ToolError`.

`inspect_dataset` does not mutate `AgentState` — these views are ephemeral, attached to the chat message that produced them, like every other CopilotKit-rendered tool result.

## 3. Module structure

```
backend/geo_agent/agent/tools/
  __init__.py            # re-exports every tool; graph.py imports from here
  wfs/
    __init__.py
    list_layers.py       # list_wfs_layers
    describe_layer.py     # describe_wfs_layer            (new)
    select_features.py    # select_features  (+ PolygonSource, DatasetSource, AttributeFilterInput)
  datasets/
    __init__.py
    filter_attributes.py  # filter_attributes
    aggregate.py          # aggregate
    spatial_overlay.py    # spatial_overlay  (+ OverlayInput)         (new)
    transform_geometry.py # transform_geometry (+ TransformInput)      (new)
    spatial_join.py       # spatial_join     (+ SpatialJoinInput)      (new)
    describe_dataset.py    # describe_dataset
    list_datasets.py       # list_datasets
  ui/
    __init__.py
    show_on_map.py        # show_on_map, hide_on_map
    inspect_dataset.py    # inspect_dataset  (+ InspectInput)          (new)
```

`backend/geo_agent/agent/graph.py` keeps its flat `TOOLS = [...]` list but imports the names from `geo_agent.agent.tools` (the package `__init__`) rather than from individual modules. The Pydantic input models stay co-located with their tool (the convention established by the prompt-hardening work).

`backend/geo_agent/agent/tools/__init__.py` (currently empty) re-exports all 13 tools so `from geo_agent.agent.tools import select_features` etc. keeps working — tests and `graph.py` use this surface.

### 3.1 New service module

`backend/geo_agent/services/geometry_ops.py` — pure functions backed by GeoPandas + Shapely (both already dependencies), taking and returning plain GeoJSON `dict`s, mirroring the style of `services/spatial_ops.py`:

```python
def overlay(left: dict, right: dict, op: Literal["intersection","union","difference","clip"]) -> dict
def transform(geojson: dict, op: Literal["buffer","centroid","simplify","dissolve"], *,
              distance_meters: float | None = None, tolerance: float | None = None,
              by: str | None = None) -> dict
def spatial_join(left: dict, right: dict, predicate: Literal["intersects","within","contains"]) -> dict
```

Implementation notes:
- Build `GeoDataFrame`s from the feature collections with `crs="EPSG:4326"`.
- `overlay` → `gpd.overlay(left, right, how=...)` (`how="intersection"` for both `intersection` and `clip`, `how="union"`, `how="difference"`).
- `spatial_join` → `gpd.sjoin(left, right, predicate=..., how="left")`, drop the `index_right` column, suffix colliding `right` columns with `_r`, keep the first match per `left` row.
- `transform`:
  - `buffer` → `to_crs(32188)`, `.buffer(distance_meters)`, `to_crs(4326)`.
  - `centroid` → `.centroid` (computed in EPSG:32188 then reprojected back, to avoid the lat/lon centroid warning).
  - `simplify` → `.simplify(tolerance, preserve_topology=True)` in EPSG:4326.
  - `dissolve` → `gdf.dissolve(by=by)` if `by` else `gdf.dissolve()`.
- Convert back to GeoJSON via `json.loads(gdf.to_json())`; ensure the output is a JSON-safe `dict` (no numpy scalars) — the same care `filter_attributes` already takes.
- Raise `ValueError` with a clear message for bad params (missing `distance_meters`, unknown `by`, etc.); the tool layer turns that into a `bad_input` `ToolError`.

`services/spatial_ops.py` is left as-is (it holds `aggregate` and `filter_by_attribute` — lightweight, no GeoPandas).

### 3.2 Frontend changes (for `inspect_dataset`)

CopilotKit already renders per-tool widgets via `useCopilotAction({ name, render })`. Add one renderer for `inspect_dataset` that dispatches on `args.view`:

| `view` | Widget | Data source | Status |
|---|---|---|---|
| `schema` | `SchemaWidget` (existing) | `attribute_schema` + `sample` in the tool `result` | reused as-is |
| `feature` | `FeatureWidget` (**new**) | `{index, properties, geometry_type, vertex_count}` in `result` | new — `frontend/components/Widgets/FeatureWidget.tsx`: property table + geometry summary; a chat-resident sibling of `FeatureDrawer` minus the map bits |
| `features` | `FeatureListWidget` (**new**) | `{features: [{index, properties, geometry_type}], total}` in `result` | new — `frontend/components/Widgets/FeatureListWidget.tsx`: compact table; clicking a row expands that feature's properties; shows `total` when it exceeds the 50-row cap |

- `frontend/components/GeoPage.tsx` — register the `inspect_dataset` `useCopilotAction` renderer that switches on `args.view`.
- `frontend/lib/types.ts` — add the `inspect_dataset` payload types (`InspectSchemaResult`, `InspectFeaturesResult`, `InspectFeatureResult`).
- The "Voir le schéma" button on `MetadataWidget` stays (local composition, no LLM round-trip); `inspect_dataset(view=schema)` is just the agent-driven path to the same `SchemaWidget`.
- `SchemaWidget`'s lazy per-attribute stats still use `GET /api/datasets/[id]/attributes/[name]/stats` (unchanged).
- No new REST endpoint, no `AgentState` change.

### 3.3 System prompt (`backend/geo_agent/agent/prompts.py`)

Rewrite the `# Tool catalog` section to mirror the three families:

```
# Tool catalog

## WFS server tools (remote — query Montreal's geomatics server)
  ## list_wfs_layers    ...
  ## describe_wfs_layer  ...   (with one JSON example)
  ## select_features     ...   (existing examples kept)

## Local dataset tools (in-memory — operate on datasets you already produced)
  ## filter_attributes   ...
  ## aggregate           ...
  ## spatial_overlay     ...   (one JSON example per typical op, esp. intersection)
  ## transform_geometry  ...   (one JSON example: buffer with distance_meters)
  ## spatial_join        ...   (one JSON example)
  ## describe_dataset    ...
  ## list_datasets       ...

## UI tools (surface a view to the user)
  ## show_on_map / hide_on_map  ...
  ## inspect_dataset            ...  (one JSON example per view)
```

Also:
- In `# Core rules`, add: *to slice or transform data you already have, prefer the local dataset tools over re-querying the WFS*; and *call `describe_wfs_layer` before a `select_features` with an `attribute_filter` if you don't know the attribute names* (the WFS parallel of the existing `describe_dataset`-before-`filter_attributes` rule).
- In `# Error handling`, add `empty_result` → loosen the criterion or change approach; never retry the same call.
- Note that `transform_geometry` with `op=buffer` requires `distance_meters` and that distances are in metres; `simplify`'s `tolerance` is in degrees.

## 4. What does not change

- `select_features`, `filter_attributes`, `aggregate`, `describe_dataset`, `list_datasets`, `show_on_map`, `hide_on_map` — behaviour unchanged, only the file location and the `tools/__init__.py` re-export.
- `AgentState`, `result_store`, the SSE protocol, the REST routes.
- `services/spatial_ops.py`, `services/ogc_filter.py`, `services/wfs_client.py`.
- The existing frontend widgets (`MetadataWidget`, `SchemaWidget`, `AttributeStatsRow`) and map components.

## 5. Testing

**Backend unit (pytest):**
- `services/geometry_ops.py` — on synthetic GeoJSONs: `overlay` (intersection of a line set with a polygon; union; difference; clip == intersection), `transform` (buffer area grows; centroid is a Point inside the original; simplify reduces vertex count; dissolve-by collapses to one feature per key), `spatial_join` (left feature gets right's attribute; non-matching left feature gets nulls; colliding columns suffixed `_r`). Bad params raise `ValueError`.
- `tools/wfs/describe_layer.py` — returns the attribute list from a mocked `describe_feature_type`; unknown layer → `layer_not_found` `ToolError`. `args_schema` validation.
- `tools/datasets/spatial_overlay.py`, `transform_geometry.py`, `spatial_join.py` — `args_schema` rejects unknown `op` / `predicate`; happy path persists a dataset with the right `lineage.parent_ids` / `operation` / `params` and returns a `dataset_created_command`; `dataset_not_found` on a missing input; `empty_result` from a non-overlapping overlay; `bad_input` from `buffer` without `distance_meters`.
- `tools/ui/inspect_dataset.py` — `args_schema` rejects unknown `view`; each `view` returns the documented compact shape with no coordinates; out-of-range `feature_index` → `bad_input`; missing dataset → `dataset_not_found`.
- `agent/prompts.py` (`test_prompt_builder.py`) — `SYSTEM_PROMPT` contains the three family headers, the five new tool names, and the `empty_result` code.
- Imports: `from geo_agent.agent.tools import <every tool name>` resolves (a guard test that the `__init__` re-export is complete).

**Frontend unit (Vitest):**
- `FeatureWidget` renders the property table and the geometry summary from a sample payload.
- `FeatureListWidget` renders N rows, shows `total` when it exceeds the cap, and expands a row on click.
- The `inspect_dataset` renderer dispatches: `view=schema` → `SchemaWidget`, `view=feature` → `FeatureWidget`, `view=features` → `FeatureListWidget`.

**E2E (Playwright):** optional, matching the prompt-hardening plan's "unit-only" stance. If added: draw a polygon → "buffer it by 100 m and show it" → assert a new layer appears; "show me the schema of <dataset>" → assert a `SchemaWidget` renders in the chat.

**Verification gate before completion:** `cd backend && uv run pytest -q` (0 failures), `cd backend && uv run ruff check geo_agent tests` (clean), `cd frontend && npm test` (or the project's vitest command) green.

## 6. Out of scope (v1)

- `how`/one-to-many semantics for `spatial_join` (first match wins).
- Three-or-more-input overlays (chain `spatial_overlay` calls).
- Persisting `inspect_dataset` views across turns / a side panel for them (they're inline-chat, ephemeral).
- A `state`-backed "inspector" panel like `active_layers`.
- Reprojection options beyond EPSG:32188 for metric ops (good enough for Montreal).
- New REST endpoints; `inspect_dataset` ships its payload through the tool result.
- Editing feature properties (read-only everywhere).

## 7. Notable design choices

1. **Consolidated verbs over many tools.** `spatial_overlay(op=...)` instead of four tools; `transform_geometry(op=...)` instead of four; `inspect_dataset(view=...)` instead of three. 13 tools total — keeps tool-calling reliable on the 7B local model while still exposing every requested capability. The cost is richer schemas (discriminated `op`/`view`), which the codebase already embraces post-prompt-hardening.
2. **Three subpackages mirror the prompt.** `tools/wfs/`, `tools/datasets/`, `tools/ui/` — the file layout and the `# Tool catalog` sections tell the same story, which helps both the maintainer and (via the prompt) the LLM.
3. **`inspect_dataset` pushes a view; it does not let the agent read geometry.** It returns feature *properties* (capped, no coordinates) — enough for a useful chat widget, consistent with "the agent never sees GeoJSON".
4. **Local ops are first-class dataset producers.** `spatial_overlay` / `transform_geometry` / `spatial_join` write numbered datasets with two-parent lineage, exactly like `select_features` — chains stay traceable.
5. **Metric operations reproject to EPSG:32188.** Buffer-in-metres is meaningless in EPSG:4326; the Montreal MTM zone 8 CRS is the standard local metric reference.
6. **No backend protocol or state changes.** Everything rides the existing tool-result + `dataset_created_command` + CopilotKit-render machinery; the redesign is additive plus a file move.
