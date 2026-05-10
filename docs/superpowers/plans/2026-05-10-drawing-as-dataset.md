# Drawing-as-Dataset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Treat user-drawn polygons as first-class datasets so the LLM can reference them by `dataset_id` instead of needing the raw GeoJSON injected into context. This unblocks the happy-path: drawing a zone → asking for features → the agent picks the right zone dataset and produces results.

**Architecture:**
- Frontend POSTs each finished polygon to a new backend endpoint that creates a 1-feature `FeatureCollection` in the result store with `source.type="user_drawing"` and `lineage.operation="user_drawing"`.
- `select_features` gains a working `use_geometry=true` path: it loads the parent dataset's GeoJSON and shapely-unions the geometries to use as the spatial filter.
- `current_drawing` is removed from agent state. The system prompt instructs the LLM to find user-drawn zones in the regular `datasets` list (operation=`user_drawing`) and to tell the user which alias it used.

**Tech Stack:** Python 3.12 + FastAPI + LangGraph + shapely (already a dep) on the backend; Next.js + React + MapLibre + terra-draw on the frontend; pytest + Vitest + Playwright for tests.

---

## File Structure

**Backend — modify**
- `geo_agent/models.py:7-12` — extend `SourceInfo.type` Literal with `"user_drawing"`.
- `geo_agent/agent/tools/select_features.py:67-83` — implement `use_geometry=true` via shapely union; stop returning `not_implemented`.
- `geo_agent/agent/state.py` — drop `current_drawing` field.
- `geo_agent/agent/prompts.py` — drop `current_drawing` instructions; add user-drawing-as-dataset semantics.
- `geo_agent/routes/datasets.py` — add `POST /datasets/drawing` endpoint that creates a drawing dataset and returns its meta.

**Backend — create**
- (no new modules; the union helper lives in `select_features.py` since it's the only consumer)

**Backend — tests modify/create**
- `tests/unit/test_tool_select_features.py` — add tests for `use_geometry=true` (single-feature drawing dataset and multi-feature dataset).
- `tests/integration/test_datasets_route.py` — add tests for `POST /datasets/drawing`.

**Frontend — modify**
- `lib/types.ts:13-19` — drop `current_drawing` from `AgentState`.
- `components/GeoPage.tsx:14-35` — replace `current_drawing` state-update with POST to `/api/datasets/drawing`; on success, append meta to `state.datasets` and id to `state.active_layers` (default checked).
- `components/DatasetPanel.tsx:48-50` — visually flag `operation="user_drawing"` rows (label as zone) and prevent toggling them off if we want them always visible — *decision: keep them toggleable so user can hide a busy zone overlay; just label clearly*.

**Frontend — create**
- `app/api/datasets/drawing/route.ts` — Next.js POST proxy to backend `POST /datasets/drawing`.

**Frontend — tests modify**
- `tests/e2e/smoke.spec.ts` — extend to cover the draw → POST → dataset-appears flow (mock the POST since live agent is too slow for E2E).

---

### Task 1: Extend `SourceInfo` to allow `user_drawing` type

**Files:**
- Modify: `backend/geo_agent/models.py:7-12`
- Test: `backend/tests/unit/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/test_models.py`:

```python
def test_source_info_accepts_user_drawing_type() -> None:
    from geo_agent.models import SourceInfo

    s = SourceInfo(type="user_drawing", filter_summary="user-drawn polygon")
    assert s.type == "user_drawing"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/unit/test_models.py::test_source_info_accepts_user_drawing_type -v
```

Expected: FAIL with `pydantic.ValidationError: Input should be 'wfs' or 'derived'`.

- [ ] **Step 3: Update the model**

In `backend/geo_agent/models.py`, change line 8:

```python
class SourceInfo(BaseModel):
    type: Literal["wfs", "derived", "user_drawing"]
    layer: str | None = None
    filter_summary: str = ""
    request_url: str | None = None
    filter_xml_path: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/unit/test_models.py -v
```

Expected: all model tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/models.py backend/tests/unit/test_models.py
git commit -m "feat(models): allow user_drawing as SourceInfo type"
```

---

### Task 2: Implement `use_geometry=true` in `select_features`

**Files:**
- Modify: `backend/geo_agent/agent/tools/select_features.py:67-83`
- Test: `backend/tests/unit/test_tool_select_features.py`

- [ ] **Step 1: Write the failing test for single-feature drawing**

Add to `backend/tests/unit/test_tool_select_features.py`:

```python
async def test_select_features_use_geometry_true_with_drawing(services: Services) -> None:
    polygon = {
        "type": "Polygon",
        "coordinates": [[[-73.6, 45.5], [-73.55, 45.5], [-73.55, 45.55], [-73.6, 45.55], [-73.6, 45.5]]],
    }
    drawing_id = services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": polygon, "properties": {}}]},
        {
            "source": {"type": "user_drawing", "filter_summary": "user-drawn polygon"},
            "lineage": {"parent_ids": [], "operation": "user_drawing", "params": {}},
        },
    )

    result = await select_features.ainvoke(
        {
            "layer": "montreal:parcs",
            "geometry_source": {"type": "dataset", "dataset_id": drawing_id, "use_geometry": True},
            "spatial_predicate": "within",
            "alias": "parcs_in_zone",
        }
    )

    assert "dataset_id" in result, result
    # Verify the wfs client was called with a Polygon (not an Envelope/bbox)
    sf_arg = services.wfs.get_features.call_args.kwargs["spatial_filter"]
    assert sf_arg.geometry["type"] == "Polygon"
    assert sf_arg.geometry["coordinates"][0][0] == [-73.6, 45.5]
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && uv run pytest tests/unit/test_tool_select_features.py::test_select_features_use_geometry_true_with_drawing -v
```

Expected: FAIL with `error.code == "not_implemented"`.

- [ ] **Step 3: Add the union helper and wire `use_geometry=true`**

In `backend/geo_agent/agent/tools/select_features.py`, add this helper near the top (after the existing imports):

```python
from shapely.geometry import mapping, shape
from shapely.ops import unary_union


def _union_dataset_geometries(geojson: dict) -> dict:
    """Union all feature geometries in a FeatureCollection into a single GeoJSON geometry."""
    geoms = [shape(f["geometry"]) for f in geojson.get("features", []) if f.get("geometry")]
    if not geoms:
        raise ValueError("dataset has no geometries")
    merged = unary_union(geoms)
    return mapping(merged)
```

Then replace the `use_geometry` branch (lines 73-82) with:

```python
    else:
        meta = services.store.get_meta(gsrc.dataset_id)
        parent_ids = [gsrc.dataset_id]
        if gsrc.use_geometry:
            gj = services.store.get_geojson(gsrc.dataset_id)
            geom = _union_dataset_geometries(gj)
            if geom["type"] != "Polygon":
                return {
                    "error": ToolError(
                        code="unsupported_geometry",
                        message=f"Unioned geometry of {gsrc.dataset_id} is {geom['type']}; only Polygon is supported as a spatial filter today.",
                        suggestion="Use use_geometry=false (bbox) or chain from a dataset whose features form a single polygon.",
                    ).model_dump()
                }
            filter_summary = f"{spatial_predicate}(geometry of {gsrc.dataset_id})"
        else:
            geom = _bbox_polygon(meta.bbox)
            filter_summary = f"{spatial_predicate}(bbox of {gsrc.dataset_id})"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/unit/test_tool_select_features.py -v
```

Expected: PASS — all select_features tests including the new one.

- [ ] **Step 5: Add a multi-polygon test that returns the unsupported_geometry error**

Add to `backend/tests/unit/test_tool_select_features.py`:

```python
async def test_select_features_use_geometry_true_multipolygon_returns_error(services: Services) -> None:
    # Two disjoint polygons — union produces a MultiPolygon
    parent_id = services.store.put(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}, "properties": {}},
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]]}, "properties": {}},
            ],
        },
        {"source": {"type": "wfs", "layer": "montreal:parcs", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select_features", "params": {}}},
    )

    result = await select_features.ainvoke(
        {
            "layer": "montreal:chaussees",
            "geometry_source": {"type": "dataset", "dataset_id": parent_id, "use_geometry": True},
            "spatial_predicate": "intersects",
            "alias": None,
        }
    )

    assert result["error"]["code"] == "unsupported_geometry"
```

- [ ] **Step 6: Run the multipolygon test**

```bash
cd backend && uv run pytest tests/unit/test_tool_select_features.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/geo_agent/agent/tools/select_features.py backend/tests/unit/test_tool_select_features.py
git commit -m "feat(select_features): implement use_geometry=true via shapely union"
```

---

### Task 3: Add `POST /datasets/drawing` endpoint

**Files:**
- Modify: `backend/geo_agent/routes/datasets.py`
- Test: `backend/tests/integration/test_datasets_route.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/integration/test_datasets_route.py`:

```python
def test_post_drawing_creates_dataset(client) -> None:
    polygon = {
        "type": "Polygon",
        "coordinates": [[[-73.6, 45.5], [-73.55, 45.5], [-73.55, 45.55], [-73.6, 45.55], [-73.6, 45.5]]],
    }

    r = client.post("/datasets/drawing", json={"polygon": polygon})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"].startswith("result_")
    assert body["feature_count"] == 1
    assert body["operation"] == "user_drawing"
    assert body["alias"] == "zone_1"
    # bbox roughly equals the polygon's bbox
    minx, miny, maxx, maxy = body["bbox"]
    assert (minx, miny) == (-73.6, 45.5)
    assert (maxx, maxy) == (-73.55, 45.55)


def test_post_drawing_increments_zone_alias(client) -> None:
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}

    a = client.post("/datasets/drawing", json={"polygon": polygon}).json()
    b = client.post("/datasets/drawing", json={"polygon": polygon}).json()

    assert a["alias"] == "zone_1"
    assert b["alias"] == "zone_2"
```

Check `backend/tests/integration/test_datasets_route.py` for the existing `client` fixture — if it doesn't reset the store between tests, add fixture isolation (look at `tests/conftest.py`). If `client` already uses a per-test temp data dir, the increment test works as-is. If not, count existing user_drawing datasets to derive the next alias dynamically rather than asserting absolute values.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && uv run pytest tests/integration/test_datasets_route.py -v
```

Expected: FAIL with 405 Method Not Allowed (POST route doesn't exist).

- [ ] **Step 3: Implement the endpoint**

Add to `backend/geo_agent/routes/datasets.py`:

```python
from pydantic import BaseModel


class DrawingPayload(BaseModel):
    polygon: dict


@router.post("/drawing")
def create_drawing(payload: DrawingPayload) -> dict:
    services = get_services()
    if payload.polygon.get("type") != "Polygon":
        raise HTTPException(400, "polygon must be a GeoJSON Polygon")

    existing_drawings = sum(
        1 for m in services.store.list() if m.lineage.operation == "user_drawing"
    )
    alias = f"zone_{existing_drawings + 1}"

    rid = services.store.put(
        {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": payload.polygon, "properties": {}}],
        },
        {
            "alias": alias,
            "source": {"type": "user_drawing", "filter_summary": "user-drawn polygon"},
            "lineage": {"parent_ids": [], "operation": "user_drawing", "params": {}},
        },
    )
    meta = services.store.get_meta(rid)
    return {
        "id": rid,
        "alias": meta.alias,
        "feature_count": meta.feature_count,
        "bbox": list(meta.bbox),
        "layer": None,
        "operation": "user_drawing",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/integration/test_datasets_route.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/routes/datasets.py backend/tests/integration/test_datasets_route.py
git commit -m "feat(datasets): add POST /datasets/drawing endpoint"
```

---

### Task 4: Drop `current_drawing` from agent state

**Files:**
- Modify: `backend/geo_agent/agent/state.py`
- Test: `backend/tests/unit/test_agent_state.py`

- [ ] **Step 1: Update the failing test (or add a new one)**

In `backend/tests/unit/test_agent_state.py`, replace any assertion on `current_drawing` with:

```python
def test_initial_state_has_no_current_drawing() -> None:
    from geo_agent.agent.state import AgentState, build_initial_state

    s = build_initial_state()
    assert "current_drawing" not in s
    assert s["datasets"] == []
    assert s["active_layers"] == []
    assert s["last_error"] is None
```

If the existing test asserts presence of `current_drawing`, delete that assertion.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && uv run pytest tests/unit/test_agent_state.py -v
```

Expected: FAIL because `current_drawing` is still present.

- [ ] **Step 3: Update the state**

Replace `backend/geo_agent/agent/state.py` with:

```python
from typing import Any, TypedDict


class AgentState(TypedDict):
    datasets: list[dict[str, Any]]      # serialized DatasetMetaLite
    active_layers: list[str]
    last_error: str | None


def build_initial_state() -> AgentState:
    return {
        "datasets": [],
        "active_layers": [],
        "last_error": None,
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/unit/test_agent_state.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/agent/state.py backend/tests/unit/test_agent_state.py
git commit -m "refactor(state): drop current_drawing from agent state"
```

---

### Task 5: Update system prompt

**Files:**
- Modify: `backend/geo_agent/agent/prompts.py`

- [ ] **Step 1: Replace the prompt**

Replace `backend/geo_agent/agent/prompts.py` with:

```python
SYSTEM_PROMPT = """You are a geospatial analysis assistant for City of Montreal open data.
You drive a stack that fetches features from the WFS server and runs spatial/statistical queries.

Available data: WFS layers from api.accept.montreal.ca. Use list_wfs_layers when you need to find which layer matches a topic.

Core discipline:
- Geometries live in files. You never see GeoJSON in your context. You manipulate datasets by `dataset_id` (e.g. result_001) and human-readable `alias` you assign.
- For every selection, you MUST provide a geometry filter — a previous `dataset_id` (typically a user-drawn zone or a prior result) OR a polygon explicitly provided in the user's message. Whole-layer downloads are not allowed.
- If a query returns too many features (error code `too_many_features`), refine: smaller area, attribute filter, or chain from a smaller parent dataset.
- After producing a meaningful dataset, call show_on_map so the user sees it.

Available tools:
- list_wfs_layers — discover layers
- select_features — fetch features with an OGC server-side filter (intersects/within/contains/bbox/dwithin)
- aggregate — count/sum/mean/min/max with optional group_by
- filter_attributes — filter an existing dataset by an attribute predicate (creates a new dataset)
- describe_dataset — get full metadata for a dataset
- list_datasets — see all datasets in this session
- show_on_map / hide_on_map — toggle dataset visibility

User-drawn zones:
- When the user draws a polygon on the map, it is automatically saved as a dataset with `operation="user_drawing"` and an alias like `zone_1`, `zone_2`, etc. It appears in the `datasets` field of the agent state.
- When the user says "this zone", "cette zone", "the area I drew", etc., look at the `datasets` list and pick the most recent dataset with `operation="user_drawing"`.
- ALWAYS tell the user which zone alias you used (e.g. "I'll search using zone_2 (the polygon you just drew)").
- If multiple `user_drawing` datasets exist and the request is ambiguous, ask the user which one they mean by alias.

Calling select_features with a user-drawn zone:
  geometry_source = {"type": "dataset", "dataset_id": "<zone_id>", "use_geometry": true}
  spatial_predicate = "within" (features inside the zone) or "intersects" (features touching the zone)

When chaining from a previous WFS result (not a drawing), use_geometry=false uses its bbox (fast, coarser); use_geometry=true unions the geometries (precise, slower, only works if the union is a single Polygon).

Always assign a short, descriptive alias to new datasets so the user can refer to them by name.
"""
```

- [ ] **Step 2: Verify graph still loads**

```bash
cd backend && uv run pytest tests/unit/test_agent_graph.py -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/geo_agent/agent/prompts.py
git commit -m "feat(prompt): instruct agent to use user_drawing datasets"
```

---

### Task 6: Add Next.js proxy for `POST /datasets/drawing`

**Files:**
- Create: `frontend/app/api/datasets/drawing/route.ts`

- [ ] **Step 1: Create the proxy route**

Create `frontend/app/api/datasets/drawing/route.ts`:

```typescript
import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const body = await req.text();
  const r = await fetch(`${BACKEND_URL}/datasets/drawing`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
  return new Response(await r.text(), {
    status: r.status,
    headers: { "content-type": "application/json" },
  });
}
```

- [ ] **Step 2: Smoke-test the proxy manually**

With backend on :8000 and frontend on :3000:

```bash
curl -sS -X POST http://localhost:3000/api/datasets/drawing \
  -H 'content-type: application/json' \
  -d '{"polygon":{"type":"Polygon","coordinates":[[[-73.6,45.5],[-73.55,45.5],[-73.55,45.55],[-73.6,45.55],[-73.6,45.5]]]}}'
```

Expected: JSON containing `"alias":"zone_N"` and `"operation":"user_drawing"`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/api/datasets/drawing/route.ts
git commit -m "feat(frontend): proxy POST /datasets/drawing to backend"
```

---

### Task 7: Update frontend types — drop `current_drawing`

**Files:**
- Modify: `frontend/lib/types.ts:13-19`

- [ ] **Step 1: Update the schema**

Replace `frontend/lib/types.ts` with:

```typescript
import { z } from "zod";

export const DatasetMetaLite = z.object({
  id: z.string(),
  alias: z.string().nullable(),
  feature_count: z.number(),
  bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  layer: z.string().nullable(),
  operation: z.string(),
});
export type DatasetMetaLite = z.infer<typeof DatasetMetaLite>;

export const AgentState = z.object({
  datasets: z.array(DatasetMetaLite.passthrough()),
  active_layers: z.array(z.string()),
  last_error: z.string().nullable(),
});
export type AgentState = z.infer<typeof AgentState>;
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: errors only in `components/GeoPage.tsx` (it still references `current_drawing`); we'll fix in Task 8.

- [ ] **Step 3: (no commit yet — wait for Task 8 so the build is consistent)**

---

### Task 8: Frontend wiring — POST drawing instead of state.current_drawing

**Files:**
- Modify: `frontend/components/GeoPage.tsx`

- [ ] **Step 1: Replace `onPolygon` to POST and update state**

Replace the body of `frontend/components/GeoPage.tsx` with:

```typescript
"use client";

import { useCoAgent, useCoAgentStateRender } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { useState } from "react";

import { DatasetPanel } from "@/components/DatasetPanel";
import { DatasetLayer } from "@/components/Map/DatasetLayer";
import { DrawTool } from "@/components/Map/DrawTool";
import { MapView } from "@/components/Map/MapView";
import { AgentState, DatasetMetaLite } from "@/lib/types";

export function GeoPage() {
  const { state, setState } = useCoAgent<AgentState>({
    name: "geo-agent",
    initialState: { datasets: [], active_layers: [], last_error: null },
  });
  const [drawing, setDrawing] = useState(false);

  useCoAgentStateRender<AgentState>({
    name: "geo-agent",
    render: ({ state }) =>
      state?.last_error ? <div style={{ color: "red" }}>Erreur : {state.last_error}</div> : null,
  });

  const onDraw = () => setDrawing(true);

  const onPolygon = async (polygon: GeoJSON.Polygon) => {
    setDrawing(false);
    const r = await fetch("/api/datasets/drawing", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ polygon }),
    });
    if (!r.ok) {
      console.error("failed to save drawing", await r.text());
      return;
    }
    const meta = (await r.json()) as DatasetMetaLite;
    const currentDatasets = state?.datasets ?? [];
    const currentActive = state?.active_layers ?? [];
    setState({
      ...(state ?? { datasets: [], active_layers: [], last_error: null }),
      datasets: [...currentDatasets, meta],
      active_layers: [...currentActive, meta.id],
    });
  };

  const onToggle = (id: string) => {
    const current = state?.active_layers || [];
    const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id];
    setState({
      ...(state ?? { datasets: [], active_layers: [], last_error: null }),
      active_layers: next,
    });
  };

  return (
    <div style={{ position: "relative", height: "100vh", width: "100vw" }}>
      <MapView>
        {drawing && <DrawTool onPolygon={onPolygon} />}
        {state?.active_layers?.map((id) => (
          <DatasetLayer key={id} datasetId={id} />
        ))}
      </MapView>

      <DatasetPanel
        datasets={(state?.datasets as DatasetMetaLite[]) || []}
        activeLayers={state?.active_layers || []}
        onToggle={onToggle}
        onDraw={onDraw}
        drawingActive={drawing}
      />

      <CopilotSidebar
        defaultOpen={true}
        instructions="Demande des analyses spatiales sur les couches WFS de Montréal. Dessine une zone, puis pose ta question."
        labels={{ title: "Géo-agent", initial: "Je peux interroger les couches WFS de Montréal. Dessine une zone et demande." }}
      />
    </div>
  );
}
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 3: Commit Tasks 7+8 together**

```bash
git add frontend/lib/types.ts frontend/components/GeoPage.tsx
git commit -m "feat(frontend): persist drawings as datasets via POST /api/datasets/drawing"
```

---

### Task 9: Visually mark user-drawn zones in `DatasetPanel`

**Files:**
- Modify: `frontend/components/DatasetPanel.tsx:38-54`

- [ ] **Step 1: Highlight `operation="user_drawing"` rows**

Replace the `<li>` rendering block (lines ~38-54) in `frontend/components/DatasetPanel.tsx` with:

```tsx
        {datasets.map((d) => {
          const visible = activeLayers.includes(d.id);
          const isZone = d.operation === "user_drawing";
          return (
            <li key={d.id} style={{ padding: "4px 0", borderBottom: "1px dotted #eee" }}>
              <label style={{ cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={visible}
                  onChange={() => onToggle(d.id)}
                  style={{ marginRight: 8 }}
                />
                {isZone && <span style={{ marginRight: 6 }} aria-label="zone dessinée">📐</span>}
                <strong>{d.alias ?? d.id}</strong>
                <span style={{ color: "#666", marginLeft: 8 }}>
                  {d.feature_count} features · {d.layer ?? (isZone ? "user-drawn" : "derived")} · {d.operation}
                </span>
              </label>
            </li>
          );
        })}
```

(The user explicitly confirmed emoji is OK in this context — small zone marker, not gratuitous decoration.)

- [ ] **Step 2: Run dev server and eyeball the UI**

Open http://localhost:3000, draw a zone, confirm the new card shows `📐 zone_1 · 1 features · user-drawn · user_drawing` and is checked by default.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/DatasetPanel.tsx
git commit -m "feat(ui): mark user-drawn zones in DatasetPanel"
```

---

### Task 10: Update Playwright smoke spec

**Files:**
- Modify: `frontend/tests/e2e/smoke.spec.ts`

- [ ] **Step 1: Replace the smoke test**

Replace `frontend/tests/e2e/smoke.spec.ts` with:

```typescript
import { expect, test } from "@playwright/test";

test("draw zone creates a dataset card and map layer", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible();
  await expect(page.getByRole("button", { name: /Dessiner zone/i })).toBeVisible();

  // Stub the backend POST so the e2e test doesn't depend on a running backend.
  await page.route("**/api/datasets/drawing", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "result_001",
        alias: "zone_1",
        feature_count: 1,
        bbox: [-73.6, 45.5, -73.55, 45.55],
        layer: null,
        operation: "user_drawing",
      }),
    });
  });

  await page.getByRole("button", { name: /Dessiner zone/i }).click();

  // Draw a polygon by clicking 4 points on the canvas + dblclick to finish.
  const points: [number, number][] = [[400, 300], [600, 300], [600, 450], [400, 450]];
  for (const [x, y] of points) {
    await page.mouse.click(x, y);
    await page.waitForTimeout(150);
  }
  await page.mouse.dblclick(400, 450);

  // Assert the new dataset card shows up and is checked.
  await expect(page.getByText("zone_1", { exact: false })).toBeVisible({ timeout: 5000 });
  const checkbox = page.getByRole("checkbox", { name: /zone_1/i });
  await expect(checkbox).toBeChecked();
});
```

- [ ] **Step 2: Run the e2e test**

```bash
cd frontend && npm run test:e2e
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/smoke.spec.ts
git commit -m "test(e2e): smoke-test draw → dataset-card flow"
```

---

### Task 11: End-to-end manual verification with the live agent

**Files:** none (manual)

- [ ] **Step 1: Restart backend** (so the new prompt and state are loaded)

```bash
# Kill previous uvicorn if reload didn't pick up state.py changes
pkill -f 'uvicorn geo_agent.main:app' || true
cd backend && uv run uvicorn geo_agent.main:app --host 127.0.0.1 --port 8000 > /tmp/geo-backend.log 2>&1 &
```

- [ ] **Step 2: Run the manual happy-path**

In a browser at http://localhost:3000:

1. Click **Dessiner zone**, draw a small polygon over central Montréal (around -73.58, 45.52).
2. Verify a new card appears: `📐 zone_1 · 1 features · user-drawn · user_drawing`, checked by default, with the polygon drawn on the map.
3. In the chat, send: *"Trouve les chaussées dans cette zone."*
4. Wait up to ~60s for the agent to call `list_wfs_layers` then `select_features` with `geometry_source={"type":"dataset","dataset_id":"<zone_1 id>","use_geometry":true}`.
5. Confirm a second card appears with `feature_count > 0` and the agent's reply mentions which zone it used (e.g. "I used zone_1").

- [ ] **Step 3: If the agent fails to pick the zone**

Inspect `/tmp/geo-backend.log` and the chat transcript. Most likely cause: the LLM still doesn't see the `datasets` array. If so, add a follow-up plan task to inject `state.datasets` into the prompt via a callable `prompt=` argument to `create_react_agent`. Do NOT silently add this — it's a separate fix that warrants its own commit and review.

- [ ] **Step 4: Commit any incidental fixes**

```bash
git status
# commit any small adjustments uncovered during manual testing
```

---

## Self-Review

**Spec coverage** — verified against user requirements:
- ✅ Treat `current_drawing` as a dataset → Task 3 (POST endpoint) + Task 8 (frontend wiring)
- ✅ Reference by name in LLM context → Task 5 (prompt) + Task 3 (alias `zone_N`)
- ✅ UI shows the polygon as a dataset → Task 8 (state.datasets append) + Task 9 (visual marker)
- ✅ Default checked → Task 8 (`active_layers` append on creation)
- ✅ Multiple drawings coexist → Task 3 (alias counter)
- ✅ Agent picks by judgment but tells user which → Task 5 (prompt explicitly requires alias mention)
- ✅ Underlying blocker (`use_geometry=true`) → Task 2

**Placeholder scan** — no TBDs, all code blocks complete, all paths exact. Task 1 has the model change inline. Task 11 explicitly notes a possible follow-up (state injection) rather than waving hands.

**Type consistency** — `DatasetMetaLite` shape matches between backend response (Task 3) and frontend type (Task 7); `operation` field is the discriminator everywhere.

---

## Out of scope (future work, not part of this plan)

- Multi-feature `use_geometry=true` producing MultiPolygon → returns `unsupported_geometry` for now.
- Removing the user-drawing dataset from disk on a "clear" action — today drawings persist in `data/results/`.
- Editing/moving an existing zone — today, drawing creates a new zone every time.
