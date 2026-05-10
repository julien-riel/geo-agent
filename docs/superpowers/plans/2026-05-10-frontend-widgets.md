# Frontend widgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build three specialised widgets (`MetadataWidget`, `SchemaWidget`, `FeaturePopup`+`FeatureDrawer`) so users can inspect dataset metadata, attribute schemas, and individual features with on-map highlight.

**Architecture:** The two chat widgets piggyback on existing tool results via CopilotKit's `useCopilotAction({ name, render })`. The feature inspector is map-driven (popup → drawer), with a dedicated MapLibre highlight source. One new backend endpoint (`/datasets/{id}/attributes/{name}/stats`) supports the schema widget's expand mode.

**Tech Stack:** Next.js 16 + React 19, CopilotKit 1.5, MapLibre GL 5, FastAPI 0.115, Pydantic 2, Vitest + jsdom for component tests, Playwright for e2e, pytest for backend.

**Spec:** `docs/superpowers/specs/2026-05-10-frontend-widgets-design.md`

---

## File Structure

### New files

```
backend/
  geo_agent/services/attribute_stats.py         # pure compute: GeoJSON + attr → stats dict
  tests/unit/test_attribute_stats.py
  tests/integration/test_route_attribute_stats.py

frontend/
  components/Widgets/MetadataWidget.tsx
  components/Widgets/SchemaWidget.tsx
  components/Widgets/AttributeStatsRow.tsx       # row body shown when a SchemaWidget row is expanded
  components/Map/HighlightLayer.tsx
  components/Map/FeaturePopup.tsx
  components/Map/FeatureDrawer.tsx
  lib/selectedFeature.tsx                        # React context with provider + hook
  app/api/datasets/[id]/attributes/[name]/stats/route.ts   # Next.js proxy
  tests/unit/MetadataWidget.test.tsx
  tests/unit/SchemaWidget.test.tsx
  tests/unit/HighlightLayer.test.tsx
  tests/unit/FeatureDrawer.test.tsx
  tests/e2e/feature-inspector.spec.ts
```

### Modified files

```
backend/geo_agent/routes/datasets.py   # add the new GET route
frontend/components/GeoPage.tsx        # SelectedFeatureProvider; useCopilotAction widgets; mount FeatureDrawer
frontend/components/Map/MapView.tsx    # register click handlers; mount HighlightLayer + FeaturePopup
frontend/components/Map/DatasetLayer.tsx  # dim opacity when a feature in this dataset is selected
```

### Deleted files

```
frontend/components/AgentStateRenderers/DatasetCard.tsx   # replaced by MetadataWidget
```

---

## Task 1: Backend — `attribute_stats` service

Pure module that takes a GeoJSON dict and an attribute name, returns the stats dict described in spec §3.4.

**Files:**
- Create: `backend/geo_agent/services/attribute_stats.py`
- Test: `backend/tests/unit/test_attribute_stats.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_attribute_stats.py`:

```python
import pytest

from geo_agent.services.attribute_stats import compute_attribute_stats


def _gj(props_list: list[dict]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": p}
            for p in props_list
        ],
    }


def test_number_attribute_returns_min_max_distinct() -> None:
    gj = _gj([{"len": 10.0}, {"len": 20.5}, {"len": 10.0}, {"len": None}])
    s = compute_attribute_stats(gj, "len")
    assert s["attribute"] == "len"
    assert s["type"] == "number"
    assert s["non_null_count"] == 3
    assert s["null_count"] == 1
    assert s["distinct_count"] == 2
    assert s["min"] == 10.0
    assert s["max"] == 20.5
    assert "top_values" not in s  # numbers don't get top_values


def test_string_attribute_returns_top_values() -> None:
    gj = _gj([{"k": "A"}, {"k": "B"}, {"k": "A"}, {"k": "A"}, {"k": "C"}])
    s = compute_attribute_stats(gj, "k")
    assert s["type"] == "string"
    assert s["non_null_count"] == 5
    assert s["null_count"] == 0
    assert s["distinct_count"] == 3
    assert s["top_values"][0] == {"value": "A", "count": 3}
    assert {"value": "B", "count": 1} in s["top_values"]
    assert {"value": "C", "count": 1} in s["top_values"]
    assert "min" not in s


def test_boolean_attribute_treated_as_string_like() -> None:
    gj = _gj([{"on": True}, {"on": False}, {"on": True}])
    s = compute_attribute_stats(gj, "on")
    assert s["type"] == "boolean"
    assert s["non_null_count"] == 3
    assert s["distinct_count"] == 2
    assert {"value": True, "count": 2} in s["top_values"]


def test_unknown_attribute_raises_keyerror() -> None:
    gj = _gj([{"a": 1}])
    with pytest.raises(KeyError):
        compute_attribute_stats(gj, "nope")


def test_top_values_caps_at_10() -> None:
    gj = _gj([{"v": str(i % 25)} for i in range(200)])
    s = compute_attribute_stats(gj, "v")
    assert len(s["top_values"]) == 10
    # sorted desc by count
    counts = [t["count"] for t in s["top_values"]]
    assert counts == sorted(counts, reverse=True)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/unit/test_attribute_stats.py -v
```

Expected: `ModuleNotFoundError: No module named 'geo_agent.services.attribute_stats'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/geo_agent/services/attribute_stats.py`:

```python
from collections import Counter
from typing import Any


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def compute_attribute_stats(geojson: dict, attribute: str) -> dict:
    """Compute summary stats for one attribute across all features.

    Raises KeyError if no feature carries the attribute (even with a null value).
    """
    values: list[Any] = []
    null_count = 0
    found = False
    for feat in geojson.get("features", []):
        props = feat.get("properties") or {}
        if attribute not in props:
            continue
        found = True
        v = props[attribute]
        if v is None:
            null_count += 1
        else:
            values.append(v)

    if not found:
        raise KeyError(attribute)

    non_null_count = len(values)
    distinct_count = len(set(values)) if values else 0

    inferred = _infer_type(values[0]) if values else "string"

    out: dict[str, Any] = {
        "attribute": attribute,
        "type": inferred,
        "non_null_count": non_null_count,
        "null_count": null_count,
        "distinct_count": distinct_count,
    }

    if inferred == "number" and values:
        out["min"] = min(values)
        out["max"] = max(values)
    else:
        counter = Counter(values)
        out["top_values"] = [
            {"value": v, "count": c} for v, c in counter.most_common(10)
        ]

    return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/unit/test_attribute_stats.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/services/attribute_stats.py backend/tests/unit/test_attribute_stats.py
git commit -m "feat(services): add attribute_stats compute module"
```

---

## Task 2: Backend — stats route

Wire the `attribute_stats` module into a new FastAPI route.

**Files:**
- Modify: `backend/geo_agent/routes/datasets.py`
- Test: `backend/tests/integration/test_route_attribute_stats.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_route_attribute_stats.py`:

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "results").mkdir()
    (tmp_path / "sessions").mkdir()
    import importlib
    import geo_agent.main as main_mod
    importlib.reload(main_mod)
    with TestClient(main_mod.app) as c:
        yield c


def _put_dataset_with_props(props_list: list[dict]) -> str:
    from geo_agent.config import Settings
    from geo_agent.services.result_store import FileSystemResultStore

    s = Settings()
    store = FileSystemResultStore(data_dir=s.DATA_DIR)
    return store.put(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": p}
                for p in props_list
            ],
        },
        {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


def test_attribute_stats_returns_payload(client: TestClient) -> None:
    rid = _put_dataset_with_props([{"len": 1.0}, {"len": 2.0}, {"len": 3.0}])
    r = client.get(f"/datasets/{rid}/attributes/len/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["attribute"] == "len"
    assert data["type"] == "number"
    assert data["min"] == 1.0
    assert data["max"] == 3.0


def test_attribute_stats_404_when_dataset_missing(client: TestClient) -> None:
    r = client.get("/datasets/result_999/attributes/foo/stats")
    assert r.status_code == 404


def test_attribute_stats_404_when_attribute_missing(client: TestClient) -> None:
    rid = _put_dataset_with_props([{"a": 1}])
    r = client.get(f"/datasets/{rid}/attributes/nope/stats")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/integration/test_route_attribute_stats.py -v
```

Expected: 3 failed (404 on the first test because route doesn't exist yet — likely the response is 404 with a different body, but `data["attribute"] == "len"` will throw on the JSON parse / KeyError).

- [ ] **Step 3: Add the route**

Edit `backend/geo_agent/routes/datasets.py`. After `get_geojson` (around line 27), add:

```python
@router.get("/{dataset_id}/attributes/{attribute}/stats")
def get_attribute_stats(dataset_id: str, attribute: str) -> dict:
    from geo_agent.services.attribute_stats import compute_attribute_stats

    services = get_services()
    try:
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset {dataset_id} not found")
    try:
        return compute_attribute_stats(gj, attribute)
    except KeyError:
        raise HTTPException(404, f"attribute {attribute} not found in dataset {dataset_id}")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/integration/test_route_attribute_stats.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/routes/datasets.py backend/tests/integration/test_route_attribute_stats.py
git commit -m "feat(api): GET /datasets/{id}/attributes/{name}/stats endpoint"
```

---

## Task 3: Frontend — Next.js proxy for stats

Mirror the existing `/api/datasets/[id]/route.ts` pattern.

**Files:**
- Create: `frontend/app/api/datasets/[id]/attributes/[name]/stats/route.ts`

- [ ] **Step 1: Create the proxy file**

Create `frontend/app/api/datasets/[id]/attributes/[name]/stats/route.ts`:

```ts
import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ id: string; name: string }> }
) {
  const { id, name } = await ctx.params;
  const r = await fetch(
    `${BACKEND_URL}/datasets/${encodeURIComponent(id)}/attributes/${encodeURIComponent(name)}/stats`
  );
  if (!r.ok) return new Response(await r.text(), { status: r.status });
  const body = await r.text();
  return new Response(body, {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
```

- [ ] **Step 2: Sanity check (manual; backend running)**

```bash
cd frontend && npm run build
```

Expected: build succeeds, route compiles (no TS error).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/api/datasets/[id]/attributes/[name]/stats/route.ts
git commit -m "feat(frontend): add Next.js proxy for attribute stats endpoint"
```

---

## Task 4: Frontend — `MetadataWidget`

Pure React component, no map or CopilotKit dependency at this point. Wired in via `useCopilotAction` later (Task 11).

**Files:**
- Create: `frontend/components/Widgets/MetadataWidget.tsx`
- Test: `frontend/tests/unit/MetadataWidget.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/unit/MetadataWidget.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MetadataWidget } from "@/components/Widgets/MetadataWidget";

// After Task 6, the schema toggle mounts a real SchemaWidget that fetches
// /api/datasets/<id> to populate the example column. Stub it here so the
// toggle test doesn't surface unhandled rejections.
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 404 })));
});
afterEach(() => {
  vi.unstubAllGlobals();
});

const META = {
  id: "result_002",
  alias: "routes_in_zone_1",
  source: { type: "derived" as const, layer: "geobase:chaussee", filter_summary: "" },
  feature_count: 1247,
  bbox: [-73.6, 45.5, -73.55, 45.55] as [number, number, number, number],
  attribute_schema: { id_chaussee: "number", nom_voie: "string" },
  lineage: { parent_ids: ["zone_1"], operation: "select_features", params: {} },
  created_at: "2026-05-10T12:00:00Z",
  size_bytes: 412345,
};

describe("MetadataWidget", () => {
  it("renders id, alias and the three stat tiles", () => {
    render(<MetadataWidget data={META} datasetId="result_002" status="complete" />);
    expect(screen.getByText("routes_in_zone_1")).toBeInTheDocument();
    expect(screen.getByText("result_002")).toBeInTheDocument();
    expect(screen.getByText("1 247")).toBeInTheDocument(); // feature_count formatted
    expect(screen.getByText("geobase:chaussee")).toBeInTheDocument();
    expect(screen.getByText(/412/)).toBeInTheDocument(); // size in KB
  });

  it("renders the lineage breadcrumb", () => {
    render(<MetadataWidget data={META} datasetId="result_002" status="complete" />);
    expect(screen.getByText("zone_1")).toBeInTheDocument();
    expect(screen.getByText("select_features")).toBeInTheDocument();
  });

  it("calls onShowOnMap when 'Afficher sur la carte' is clicked", () => {
    const onShowOnMap = vi.fn();
    render(
      <MetadataWidget
        data={META}
        datasetId="result_002"
        status="complete"
        onShowOnMap={onShowOnMap}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /Afficher sur la carte/i }));
    expect(onShowOnMap).toHaveBeenCalledWith("result_002");
  });

  it("toggles to schema mode when 'Voir le schéma' is clicked", () => {
    render(<MetadataWidget data={META} datasetId="result_002" status="complete" />);
    fireEvent.click(screen.getByRole("button", { name: /Voir le schéma/i }));
    // Schema mode shows the attribute names
    expect(screen.getByText("id_chaussee")).toBeInTheDocument();
    expect(screen.getByText("nom_voie")).toBeInTheDocument();
  });

  it("renders a skeleton when status is executing", () => {
    render(<MetadataWidget data={META} datasetId="result_002" status="executing" />);
    expect(screen.getByTestId("metadata-skeleton")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run tests/unit/MetadataWidget.test.tsx
```

Expected: import error (`Failed to resolve import "@/components/Widgets/MetadataWidget"`).

- [ ] **Step 3: Implement the component**

Create `frontend/components/Widgets/MetadataWidget.tsx`:

```tsx
"use client";

import { useState } from "react";
import { SchemaWidget } from "./SchemaWidget";

interface DatasetMetaPayload {
  id: string;
  alias: string | null;
  source: { type: string; layer: string | null; filter_summary: string };
  feature_count: number;
  bbox: [number, number, number, number];
  attribute_schema: Record<string, string>;
  lineage: { parent_ids: string[]; operation: string; params: Record<string, unknown> };
  created_at: string;
  size_bytes: number;
}

interface Props {
  data: DatasetMetaPayload;
  datasetId: string;
  status: "executing" | "complete" | "inProgress";
  onShowOnMap?: (id: string) => void;
  onFitMap?: (bbox: [number, number, number, number]) => void;
}

function formatCount(n: number): string {
  return n.toLocaleString("fr-CA").replace(/ /g, " ").replace(/,/g, " ");
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function MetadataWidget({ data, datasetId, status, onShowOnMap, onFitMap }: Props) {
  const [showSchema, setShowSchema] = useState(false);

  if (status === "executing") {
    return (
      <div data-testid="metadata-skeleton" style={{ padding: 12, background: "#f1f5f9", borderRadius: 8 }}>
        <em style={{ color: "#94a3b8" }}>Chargement…</em>
      </div>
    );
  }

  if (showSchema) {
    return <SchemaWidget data={data} datasetId={datasetId} />;
  }

  const layerLabel = data.source?.layer ?? data.lineage.operation;

  return (
    <div style={{ background: "#f8fafc", padding: 16, borderRadius: 8, fontFamily: "system-ui", fontSize: 13, color: "#0f172a" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={{ background: "#3b82f6", color: "white", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 }}>DATASET</span>
        <strong style={{ fontSize: 15 }}>{data.alias ?? data.id}</strong>
        <span style={{ color: "#64748b", fontFamily: "monospace", fontSize: 11 }}>{data.id}</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, marginBottom: 12 }}>
        <Tile label="Features" value={formatCount(data.feature_count)} />
        <Tile label="Couche" value={layerLabel} />
        <Tile label="Taille" value={formatSize(data.size_bytes)} />
      </div>

      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>Lignée</div>
        <Lineage parents={data.lineage.parent_ids} operation={data.lineage.operation} current={data.alias ?? data.id} />
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button onClick={() => setShowSchema(true)} style={btnPrimary}>Voir le schéma</button>
        <button onClick={() => onShowOnMap?.(datasetId)} style={btnSecondary}>Afficher sur la carte</button>
        <button onClick={() => onFitMap?.(data.bbox)} style={btnSecondary}>Cadrer la carte</button>
      </div>
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: "white", padding: 8, borderRadius: 6, border: "1px solid #e2e8f0" }}>
      <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 600, color: "#0f172a" }}>{value}</div>
    </div>
  );
}

function Lineage({ parents, operation, current }: { parents: string[]; operation: string; current: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, flexWrap: "wrap" }}>
      {parents.map((p) => (
        <span key={p}>
          <span style={{ background: "#fef3c7", padding: "2px 6px", borderRadius: 3, fontFamily: "monospace" }}>{p}</span>
          <span style={{ color: "#94a3b8", margin: "0 6px" }}>→</span>
        </span>
      ))}
      <span style={{ background: "#dbeafe", padding: "2px 6px", borderRadius: 3, fontFamily: "monospace" }}>{operation}</span>
      <span style={{ color: "#94a3b8" }}>→</span>
      <span style={{ background: "#dcfce7", padding: "2px 6px", borderRadius: 3, fontFamily: "monospace", fontWeight: 600 }}>{current}</span>
    </div>
  );
}

const btnPrimary = { background: "#3b82f6", color: "white", border: "none", padding: "6px 12px", borderRadius: 5, fontSize: 12, cursor: "pointer" } as const;
const btnSecondary = { background: "white", border: "1px solid #e2e8f0", color: "#0f172a", padding: "6px 12px", borderRadius: 5, fontSize: 12, cursor: "pointer" } as const;
```

- [ ] **Step 4: Stub `SchemaWidget`**

The MetadataWidget imports `SchemaWidget`. Create a temporary stub at `frontend/components/Widgets/SchemaWidget.tsx`:

```tsx
"use client";

interface Props {
  data: { attribute_schema: Record<string, string> };
  datasetId: string;
}

export function SchemaWidget({ data }: Props) {
  return (
    <div>
      {Object.keys(data.attribute_schema).map((k) => (
        <div key={k}>{k}</div>
      ))}
    </div>
  );
}
```

This stub is enough to make the toggle test pass. Task 6 replaces it with the real component.

- [ ] **Step 5: Run test to verify it passes**

```bash
cd frontend && npx vitest run tests/unit/MetadataWidget.test.tsx
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/Widgets/MetadataWidget.tsx frontend/components/Widgets/SchemaWidget.tsx frontend/tests/unit/MetadataWidget.test.tsx
git commit -m "feat(widgets): add MetadataWidget with stat tiles, lineage and schema toggle"
```

---

## Task 5: Frontend — `AttributeStatsRow`

Helper component shown beneath a SchemaWidget row when expanded. Owns the lazy fetch and rendering of the stats payload.

**Files:**
- Create: `frontend/components/Widgets/AttributeStatsRow.tsx`

(No standalone test file — covered indirectly by the SchemaWidget test in Task 6 via `vi.fn()` for fetch.)

- [ ] **Step 1: Implement the component**

Create `frontend/components/Widgets/AttributeStatsRow.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";

interface Stats {
  attribute: string;
  type: "number" | "string" | "boolean";
  non_null_count: number;
  null_count: number;
  distinct_count: number;
  min?: number;
  max?: number;
  top_values?: Array<{ value: unknown; count: number }>;
}

interface Props {
  datasetId: string;
  attribute: string;
}

export function AttributeStatsRow({ datasetId, attribute }: Props) {
  const [state, setState] = useState<{ kind: "loading" } | { kind: "ok"; stats: Stats } | { kind: "error"; message: string }>({ kind: "loading" });

  useEffect(() => {
    fetch(`/api/datasets/${encodeURIComponent(datasetId)}/attributes/${encodeURIComponent(attribute)}/stats`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((stats: Stats) => setState({ kind: "ok", stats }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }, [datasetId, attribute]);

  if (state.kind === "loading") {
    return <div style={{ padding: "6px 10px", fontSize: 11, color: "#64748b", fontStyle: "italic" }}>Chargement des stats…</div>;
  }
  if (state.kind === "error") {
    return <div style={{ padding: "6px 10px", fontSize: 11, color: "#b91c1c" }}>Erreur : {state.message}</div>;
  }

  const s = state.stats;

  return (
    <div style={{ padding: "8px 10px", background: "#f8fafc", borderTop: "1px solid #e2e8f0", fontSize: 11 }}>
      <div style={{ display: "flex", gap: 16, color: "#475569" }}>
        <span>Non null : <strong>{s.non_null_count}</strong></span>
        <span>Null : <strong>{s.null_count}</strong></span>
        <span>Distinctes : <strong>{s.distinct_count}</strong></span>
        {s.min !== undefined && <span>Min : <strong>{s.min}</strong></span>}
        {s.max !== undefined && <span>Max : <strong>{s.max}</strong></span>}
      </div>
      {s.top_values && s.top_values.length > 0 && (
        <div style={{ marginTop: 6 }}>
          <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 2 }}>Top valeurs</div>
          <ul style={{ margin: 0, paddingLeft: 16, color: "#0f172a" }}>
            {s.top_values.slice(0, 5).map((tv, i) => (
              <li key={i}><code>{String(tv.value)}</code> · {tv.count}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit (will be tested via SchemaWidget in Task 6)**

```bash
git add frontend/components/Widgets/AttributeStatsRow.tsx
git commit -m "feat(widgets): add AttributeStatsRow with lazy stats fetch"
```

---

## Task 6: Frontend — `SchemaWidget` (real)

Replace the stub from Task 4 with the full component: 3-column table, lazy GeoJSON fetch for example values, expandable rows.

**Files:**
- Replace: `frontend/components/Widgets/SchemaWidget.tsx`
- Test: `frontend/tests/unit/SchemaWidget.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/unit/SchemaWidget.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SchemaWidget } from "@/components/Widgets/SchemaWidget";

const DATA = {
  id: "result_002",
  alias: "routes",
  attribute_schema: { id_chaussee: "number", nom_voie: "string", en_service: "boolean" },
};

const SAMPLE_GJ = {
  type: "FeatureCollection",
  features: [{ type: "Feature", geometry: { type: "Point", coordinates: [0, 0] }, properties: { id_chaussee: 8421, nom_voie: "Rue X", en_service: true } }],
};

const SAMPLE_STATS = {
  attribute: "id_chaussee",
  type: "number",
  non_null_count: 100,
  null_count: 0,
  distinct_count: 100,
  min: 1,
  max: 100,
};

describe("SchemaWidget", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/api/datasets/result_002")) {
          return new Response(JSON.stringify(SAMPLE_GJ), { status: 200 });
        }
        if (url.includes("/attributes/id_chaussee/stats")) {
          return new Response(JSON.stringify(SAMPLE_STATS), { status: 200 });
        }
        return new Response("not found", { status: 404 });
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders one row per attribute with type chips", async () => {
    render(<SchemaWidget data={DATA} datasetId="result_002" />);
    expect(screen.getByText("id_chaussee")).toBeInTheDocument();
    expect(screen.getByText("nom_voie")).toBeInTheDocument();
    expect(screen.getByText("en_service")).toBeInTheDocument();
    expect(screen.getAllByText(/number|string|boolean/)).toHaveLength(3);
  });

  it("populates the example column from the first feature once fetched", async () => {
    render(<SchemaWidget data={DATA} datasetId="result_002" />);
    await waitFor(() => {
      expect(screen.getByText("8421")).toBeInTheDocument();
      expect(screen.getByText('"Rue X"')).toBeInTheDocument();
      expect(screen.getByText("true")).toBeInTheDocument();
    });
  });

  it("expands a row and triggers the stats fetch", async () => {
    render(<SchemaWidget data={DATA} datasetId="result_002" />);
    fireEvent.click(screen.getByText("id_chaussee"));
    await waitFor(() => {
      expect(screen.getByText(/Distinctes/)).toBeInTheDocument();
      expect(screen.getByText("100")).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run tests/unit/SchemaWidget.test.tsx
```

Expected: tests fail (the stub from Task 4 has none of the table/expand behaviour).

- [ ] **Step 3: Replace the stub with the real implementation**

Overwrite `frontend/components/Widgets/SchemaWidget.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { AttributeStatsRow } from "./AttributeStatsRow";

interface Props {
  data: {
    id: string;
    alias: string | null;
    attribute_schema: Record<string, string>;
  };
  datasetId: string;
}

const TYPE_STYLES: Record<string, { bg: string; fg: string }> = {
  number: { bg: "#dbeafe", fg: "#1e40af" },
  string: { bg: "#dcfce7", fg: "#166534" },
  boolean: { bg: "#fef3c7", fg: "#854d0e" },
};

function formatExample(v: unknown): string {
  if (v === undefined || v === null) return "—";
  if (typeof v === "string") return `"${v}"`;
  return String(v);
}

export function SchemaWidget({ data, datasetId }: Props) {
  const [example, setExample] = useState<Record<string, unknown> | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetch(`/api/datasets/${encodeURIComponent(datasetId)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("fetch failed"))))
      .then((gj) => setExample(gj.features?.[0]?.properties ?? {}))
      .catch(() => setExample({}));
  }, [datasetId]);

  const toggle = (attr: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(attr)) next.delete(attr);
      else next.add(attr);
      return next;
    });
  };

  const attrs = Object.entries(data.attribute_schema);

  return (
    <div style={{ background: "#f8fafc", padding: 16, borderRadius: 8, fontFamily: "system-ui", fontSize: 13, color: "#0f172a" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={{ background: "#8b5cf6", color: "white", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 }}>SCHÉMA</span>
        <strong style={{ fontSize: 15 }}>{data.alias ?? data.id}</strong>
        <span style={{ color: "#64748b", fontSize: 12 }}>· {attrs.length} attributs</span>
      </div>

      <div style={{ background: "white", borderRadius: 6, border: "1px solid #e2e8f0", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ background: "#f1f5f9", textAlign: "left" }}>
              <th style={th}>Attribut</th>
              <th style={th}>Type</th>
              <th style={{ ...th, textAlign: "right" }}>Exemple</th>
            </tr>
          </thead>
          <tbody>
            {attrs.map(([name, type]) => {
              const isOpen = expanded.has(name);
              const style = TYPE_STYLES[type] ?? { bg: "#e2e8f0", fg: "#0f172a" };
              return (
                <>
                  <tr
                    key={name}
                    style={{ borderTop: "1px solid #f1f5f9", cursor: "pointer" }}
                    onClick={() => toggle(name)}
                  >
                    <td style={{ padding: "6px 10px", fontFamily: "monospace", fontWeight: 500 }}>{name}</td>
                    <td style={{ padding: "6px 10px" }}>
                      <span style={{ background: style.bg, color: style.fg, padding: "1px 6px", borderRadius: 3, fontSize: 10, fontFamily: "monospace" }}>{type}</span>
                    </td>
                    <td style={{ padding: "6px 10px", textAlign: "right", color: "#64748b", fontFamily: type === "number" ? "monospace" : "inherit" }}>
                      {example ? formatExample(example[name]) : "…"}
                    </td>
                  </tr>
                  {isOpen && (
                    <tr key={`${name}-stats`}>
                      <td colSpan={3} style={{ padding: 0 }}>
                        <AttributeStatsRow datasetId={datasetId} attribute={name} />
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>

      <div style={{ fontSize: 11, color: "#64748b", marginTop: 8, fontStyle: "italic" }}>
        Échantillon tiré de la 1ʳᵉ feature. Clique une ligne pour les stats.
      </div>
    </div>
  );
}

const th: React.CSSProperties = {
  padding: "6px 10px",
  fontWeight: 600,
  color: "#475569",
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: 0.5,
};
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run tests/unit/SchemaWidget.test.tsx tests/unit/MetadataWidget.test.tsx
```

Expected: 8 passed (5 from MetadataWidget, 3 from SchemaWidget).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/Widgets/SchemaWidget.tsx frontend/tests/unit/SchemaWidget.test.tsx
git commit -m "feat(widgets): add SchemaWidget with example column and expandable stats"
```

---

## Task 7: Frontend — `SelectedFeature` context

Shared selection state consumed by `HighlightLayer`, `FeaturePopup`, `FeatureDrawer`, and `DatasetLayer` (for dimming).

**Files:**
- Create: `frontend/lib/selectedFeature.tsx`

(No dedicated test — exercised via the components and the e2e test in Task 13.)

- [ ] **Step 1: Implement context, provider, hook**

Create `frontend/lib/selectedFeature.tsx`:

```tsx
"use client";

import { createContext, ReactNode, useContext, useMemo, useState } from "react";

export interface SelectedFeature {
  datasetId: string;
  index: number;
  feature: GeoJSON.Feature;
  lngLat: [number, number];
}

interface Ctx {
  selected: SelectedFeature | null;
  setSelected: (s: SelectedFeature | null) => void;
  drawerOpen: boolean;
  setDrawerOpen: (open: boolean) => void;
}

const SelectedFeatureContext = createContext<Ctx | null>(null);

export function SelectedFeatureProvider({ children }: { children: ReactNode }) {
  const [selected, setSelectedState] = useState<SelectedFeature | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const setSelected = (s: SelectedFeature | null) => {
    setSelectedState(s);
    if (s === null) setDrawerOpen(false);
  };

  const value = useMemo(() => ({ selected, setSelected, drawerOpen, setDrawerOpen }), [selected, drawerOpen]);
  return <SelectedFeatureContext.Provider value={value}>{children}</SelectedFeatureContext.Provider>;
}

export function useSelectedFeature(): Ctx {
  const ctx = useContext(SelectedFeatureContext);
  if (!ctx) throw new Error("useSelectedFeature must be used inside SelectedFeatureProvider");
  return ctx;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/lib/selectedFeature.tsx
git commit -m "feat(state): add SelectedFeature context for cross-component selection"
```

---

## Task 8: Frontend — `HighlightLayer`

MapLibre source/layers, driven by the SelectedFeature context. Tested with a mocked map object (jsdom can't run MapLibre).

**Files:**
- Create: `frontend/components/Map/HighlightLayer.tsx`
- Test: `frontend/tests/unit/HighlightLayer.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/unit/HighlightLayer.test.tsx`:

```tsx
import { act, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HighlightLayer } from "@/components/Map/HighlightLayer";
import { MapContext } from "@/components/Map/MapView";
import { SelectedFeatureProvider, useSelectedFeature, SelectedFeature } from "@/lib/selectedFeature";
import { useEffect } from "react";

function makeFakeMap() {
  const sources = new Map<string, { type: string; data: unknown }>();
  const layers = new Set<string>();
  const setData = vi.fn();
  return {
    spy: { setData },
    map: {
      addSource: vi.fn((id: string, src: { type: string; data: unknown }) => sources.set(id, src)),
      addLayer: vi.fn((spec: { id: string }) => layers.add(spec.id)),
      removeLayer: vi.fn((id: string) => layers.delete(id)),
      removeSource: vi.fn((id: string) => sources.delete(id)),
      getSource: vi.fn((id: string) => (sources.has(id) ? { setData } : undefined)),
      getLayer: vi.fn((id: string) => (layers.has(id) ? {} : undefined)),
    } as unknown as maplibregl.Map,
  };
}

function Setter({ value }: { value: SelectedFeature | null }) {
  const { setSelected } = useSelectedFeature();
  useEffect(() => {
    setSelected(value);
  }, [value]);
  return null;
}

describe("HighlightLayer", () => {
  it("creates the highlight source and three layers on mount", () => {
    const { map } = makeFakeMap();
    render(
      <MapContext.Provider value={map}>
        <SelectedFeatureProvider>
          <HighlightLayer />
        </SelectedFeatureProvider>
      </MapContext.Provider>
    );
    expect(map.addSource).toHaveBeenCalledWith("highlight-source", expect.objectContaining({ type: "geojson" }));
    expect(map.addLayer).toHaveBeenCalledTimes(3);
  });

  it("updates the source data when a feature is selected", () => {
    const { map, spy } = makeFakeMap();
    const feature: GeoJSON.Feature = { type: "Feature", geometry: { type: "Point", coordinates: [-73, 45] }, properties: {} };
    render(
      <MapContext.Provider value={map}>
        <SelectedFeatureProvider>
          <HighlightLayer />
          <Setter value={{ datasetId: "result_001", index: 0, feature, lngLat: [-73, 45] }} />
        </SelectedFeatureProvider>
      </MapContext.Provider>
    );
    expect(spy.setData).toHaveBeenCalledWith({ type: "FeatureCollection", features: [feature] });
  });

  it("clears the source data when selection is cleared", async () => {
    const { map, spy } = makeFakeMap();
    const { rerender } = render(
      <MapContext.Provider value={map}>
        <SelectedFeatureProvider>
          <HighlightLayer />
          <Setter value={{ datasetId: "result_001", index: 0, feature: { type: "Feature", geometry: { type: "Point", coordinates: [0, 0] }, properties: {} }, lngLat: [0, 0] }} />
        </SelectedFeatureProvider>
      </MapContext.Provider>
    );
    spy.setData.mockClear();
    rerender(
      <MapContext.Provider value={map}>
        <SelectedFeatureProvider>
          <HighlightLayer />
          <Setter value={null} />
        </SelectedFeatureProvider>
      </MapContext.Provider>
    );
    expect(spy.setData).toHaveBeenCalledWith({ type: "FeatureCollection", features: [] });
  });
});
```

Note: this test imports `MapContext` from `MapView`. The current MapView doesn't export it as a named export — only `useMap`. **Step 2 fixes that.**

- [ ] **Step 2: Export `MapContext` from MapView**

Edit `frontend/components/Map/MapView.tsx`. Change line 8 from:

```tsx
const MapContext = createContext<maplibregl.Map | null>(null);
```

to:

```tsx
export const MapContext = createContext<maplibregl.Map | null>(null);
```

- [ ] **Step 3: Run test to verify it fails on the import**

```bash
cd frontend && npx vitest run tests/unit/HighlightLayer.test.tsx
```

Expected: import error (`HighlightLayer` doesn't exist).

- [ ] **Step 4: Implement the component**

Create `frontend/components/Map/HighlightLayer.tsx`:

```tsx
"use client";

import maplibregl from "maplibre-gl";
import { useEffect } from "react";
import { useSelectedFeature } from "@/lib/selectedFeature";
import { useMap } from "./MapView";

const SOURCE_ID = "highlight-source";
const LAYER_FILL = "highlight-fill";
const LAYER_LINE = "highlight-line";
const LAYER_CIRCLE = "highlight-circle";

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export function HighlightLayer() {
  const map = useMap();
  const { selected } = useSelectedFeature();

  useEffect(() => {
    if (!map) return;
    if (map.getSource(SOURCE_ID)) return;
    map.addSource(SOURCE_ID, { type: "geojson", data: EMPTY });
    map.addLayer({
      id: LAYER_FILL,
      source: SOURCE_ID,
      type: "fill",
      filter: ["==", ["geometry-type"], "Polygon"],
      paint: { "fill-color": "#fbbf24", "fill-opacity": 0.4 },
    });
    map.addLayer({
      id: LAYER_LINE,
      source: SOURCE_ID,
      type: "line",
      filter: ["==", ["geometry-type"], "LineString"],
      paint: { "line-color": "#fbbf24", "line-width": 5, "line-opacity": 0.95 },
    });
    map.addLayer({
      id: LAYER_CIRCLE,
      source: SOURCE_ID,
      type: "circle",
      filter: ["==", ["geometry-type"], "Point"],
      paint: { "circle-color": "#fbbf24", "circle-radius": 12, "circle-stroke-width": 3, "circle-stroke-color": "#92400e" },
    });
    return () => {
      for (const lid of [LAYER_FILL, LAYER_LINE, LAYER_CIRCLE]) {
        if (map.getLayer(lid)) map.removeLayer(lid);
      }
      if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
    };
  }, [map]);

  useEffect(() => {
    if (!map) return;
    const src = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    src.setData(selected ? { type: "FeatureCollection", features: [selected.feature] } : EMPTY);
  }, [map, selected]);

  return null;
}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd frontend && npx vitest run tests/unit/HighlightLayer.test.tsx
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/Map/HighlightLayer.tsx frontend/components/Map/MapView.tsx frontend/tests/unit/HighlightLayer.test.tsx
git commit -m "feat(map): add HighlightLayer driven by SelectedFeature context"
```

---

## Task 9: Frontend — `FeaturePopup`

Compact MapLibre popup anchored to the click. Mounts from inside MapView (Task 12 wires the click handler).

**Files:**
- Create: `frontend/components/Map/FeaturePopup.tsx`

(No unit test — popup creation depends on MapLibre internals; covered by the e2e test in Task 13.)

- [ ] **Step 1: Implement the component**

Create `frontend/components/Map/FeaturePopup.tsx`:

```tsx
"use client";

import maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useSelectedFeature } from "@/lib/selectedFeature";
import { useMap } from "./MapView";

function pickTitle(props: Record<string, unknown>): string {
  for (const key of ["nom_voie", "name", "nom", "title", "label"]) {
    const v = props[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  for (const key of Object.keys(props)) {
    const v = props[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  for (const key of Object.keys(props)) {
    const v = props[key];
    if (key.startsWith("id") && (typeof v === "number" || typeof v === "string")) {
      return `#${v}`;
    }
  }
  return "Feature";
}

function pickStats(props: Record<string, unknown>): Array<[string, string]> {
  const out: Array<[string, string]> = [];
  for (const [k, v] of Object.entries(props)) {
    if (out.length >= 2) break;
    if (typeof v === "number") out.push([k, String(v)]);
  }
  return out;
}

export function FeaturePopup() {
  const map = useMap();
  const { selected, setSelected, setDrawerOpen } = useSelectedFeature();
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!map || !selected) return;

    const container = document.createElement("div");
    containerRef.current = container;

    const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, anchor: "bottom" })
      .setLngLat(selected.lngLat)
      .setDOMContent(container)
      .addTo(map);

    popupRef.current = popup;

    popup.on("close", () => {
      setSelected(null);
    });

    return () => {
      popup.remove();
      popupRef.current = null;
      containerRef.current = null;
    };
  }, [map, selected?.datasetId, selected?.index]);

  if (!selected || !containerRef.current) return null;

  const props = (selected.feature.properties ?? {}) as Record<string, unknown>;
  const title = pickTitle(props);
  const stats = pickStats(props);

  return createPortal(
    <div style={{ fontFamily: "system-ui", fontSize: 11, minWidth: 160 }}>
      <div style={{ fontWeight: 600, marginBottom: 4, color: "#0f172a" }}>{title}</div>
      {stats.length > 0 && (
        <div style={{ color: "#64748b", fontSize: 10, marginBottom: 6 }}>
          {stats.map(([k, v]) => `${k}: ${v}`).join(" · ")}
        </div>
      )}
      <button
        onClick={() => setDrawerOpen(true)}
        style={{ background: "transparent", border: "none", color: "#3b82f6", fontSize: 11, cursor: "pointer", padding: 0 }}
      >
        Détails →
      </button>
    </div>,
    containerRef.current
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/Map/FeaturePopup.tsx
git commit -m "feat(map): add FeaturePopup with title, stats and Details link"
```

---

## Task 10: Frontend — `FeatureDrawer`

Right-side panel mounted at the GeoPage level. Read-only properties table, geometry summary, two action buttons.

**Files:**
- Create: `frontend/components/Map/FeatureDrawer.tsx`
- Test: `frontend/tests/unit/FeatureDrawer.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/unit/FeatureDrawer.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useEffect } from "react";

import { FeatureDrawer } from "@/components/Map/FeatureDrawer";
import { SelectedFeatureProvider, useSelectedFeature, SelectedFeature } from "@/lib/selectedFeature";

function Setter({ value, openDrawer }: { value: SelectedFeature | null; openDrawer: boolean }) {
  const { setSelected, setDrawerOpen } = useSelectedFeature();
  useEffect(() => {
    setSelected(value);
    if (value && openDrawer) setDrawerOpen(true);
  }, [value, openDrawer]);
  return null;
}

const FEATURE: GeoJSON.Feature = {
  type: "Feature",
  geometry: { type: "LineString", coordinates: [[0, 0], [1, 1], [2, 2]] },
  properties: { id_chaussee: 8421, nom_voie: "Rue X", longueur_m: 147.3 },
};

describe("FeatureDrawer", () => {
  it("does not render when no selection", () => {
    render(
      <SelectedFeatureProvider>
        <FeatureDrawer />
      </SelectedFeatureProvider>
    );
    expect(screen.queryByText(/FEATURE/)).toBeNull();
  });

  it("does not render when selection exists but drawer not opened", () => {
    render(
      <SelectedFeatureProvider>
        <FeatureDrawer />
        <Setter value={{ datasetId: "result_002", index: 7, feature: FEATURE, lngLat: [0, 0] }} openDrawer={false} />
      </SelectedFeatureProvider>
    );
    expect(screen.queryByText(/FEATURE/)).toBeNull();
  });

  it("renders title, properties, and geometry summary when open", () => {
    render(
      <SelectedFeatureProvider>
        <FeatureDrawer />
        <Setter value={{ datasetId: "result_002", index: 7, feature: FEATURE, lngLat: [0, 0] }} openDrawer={true} />
      </SelectedFeatureProvider>
    );
    expect(screen.getByText("Rue X")).toBeInTheDocument();
    expect(screen.getByText("id_chaussee")).toBeInTheDocument();
    expect(screen.getByText("8421")).toBeInTheDocument();
    expect(screen.getByText("LineString")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument(); // vertex count
  });

  it("calls onAskAgent with prefilled prompt when 'Demander à l'agent' is clicked", () => {
    const onAskAgent = vi.fn();
    render(
      <SelectedFeatureProvider>
        <FeatureDrawer onAskAgent={onAskAgent} />
        <Setter value={{ datasetId: "result_002", index: 7, feature: FEATURE, lngLat: [0, 0] }} openDrawer={true} />
      </SelectedFeatureProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: /Demander à l'agent/i }));
    expect(onAskAgent).toHaveBeenCalledWith(
      expect.stringContaining("feature #7"),
    );
    expect(onAskAgent.mock.calls[0][0]).toMatch(/result_002/);
    expect(onAskAgent.mock.calls[0][0]).toMatch(/Rue X/);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run tests/unit/FeatureDrawer.test.tsx
```

Expected: import error.

- [ ] **Step 3: Implement the component**

Create `frontend/components/Map/FeatureDrawer.tsx`:

```tsx
"use client";

import { useSelectedFeature } from "@/lib/selectedFeature";
import { useMap } from "./MapView";

interface Props {
  onAskAgent?: (prompt: string) => void;
}

function pickTitle(props: Record<string, unknown>, index: number): string {
  for (const key of ["nom_voie", "name", "nom", "title", "label"]) {
    const v = props[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  return `Feature #${index}`;
}

function countVertices(g: GeoJSON.Geometry): number {
  switch (g.type) {
    case "Point": return 1;
    case "MultiPoint": case "LineString": return g.coordinates.length;
    case "MultiLineString": case "Polygon": return g.coordinates.reduce((n, ring) => n + ring.length, 0);
    case "MultiPolygon": return g.coordinates.reduce((n, poly) => n + poly.reduce((m, ring) => m + ring.length, 0), 0);
    case "GeometryCollection": return g.geometries.reduce((n, gg) => n + countVertices(gg), 0);
    default: return 0;
  }
}

function bboxOf(g: GeoJSON.Geometry): [number, number, number, number] {
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  const walk = (c: unknown) => {
    if (Array.isArray(c) && typeof c[0] === "number" && typeof c[1] === "number") {
      const [x, y] = c as [number, number];
      if (x < minx) minx = x; if (x > maxx) maxx = x;
      if (y < miny) miny = y; if (y > maxy) maxy = y;
    } else if (Array.isArray(c)) {
      c.forEach(walk);
    }
  };
  if ("coordinates" in g) walk(g.coordinates);
  return [minx, miny, maxx, maxy];
}

export function FeatureDrawer({ onAskAgent }: Props) {
  const { selected, setSelected, drawerOpen } = useSelectedFeature();
  const map = useMap();

  if (!selected || !drawerOpen) return null;

  const props = (selected.feature.properties ?? {}) as Record<string, unknown>;
  const title = pickTitle(props, selected.index);
  const vertexCount = countVertices(selected.feature.geometry);

  const askAgent = () => {
    const prompt = `Au sujet de la feature #${selected.index} du dataset ${selected.datasetId} (« ${title} »), `;
    onAskAgent?.(prompt);
  };

  const fitMap = () => {
    if (!map) return;
    const [minx, miny, maxx, maxy] = bboxOf(selected.feature.geometry);
    if (Number.isFinite(minx)) map.fitBounds([[minx, miny], [maxx, maxy]], { padding: 80, maxZoom: 18 });
  };

  return (
    <div style={{
      position: "absolute", top: 0, right: 0, bottom: 0, width: 300,
      background: "white", borderLeft: "1px solid #e2e8f0", display: "flex", flexDirection: "column",
      fontFamily: "system-ui", fontSize: 12, color: "#0f172a", boxShadow: "-2px 0 8px rgba(0,0,0,0.05)", zIndex: 5,
    }}>
      <div style={{ padding: 12, borderBottom: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <span style={{ background: "#fbbf24", color: "#78350f", padding: "2px 6px", borderRadius: 3, fontSize: 10, fontWeight: 600 }}>FEATURE</span>
          <div style={{ fontSize: 14, fontWeight: 600, marginTop: 6 }}>{title}</div>
          <div style={{ fontSize: 10, color: "#64748b", fontFamily: "monospace", marginTop: 2 }}>{selected.datasetId} · #{selected.index}</div>
        </div>
        <button
          aria-label="Fermer"
          onClick={() => setSelected(null)}
          style={{ background: "none", border: "none", cursor: "pointer", color: "#94a3b8", fontSize: 18, lineHeight: 1 }}
        >×</button>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "8px 12px" }}>
        <div style={sectionLabel}>Propriétés</div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
          <tbody>
            {Object.entries(props).map(([k, v]) => (
              <tr key={k} style={{ borderBottom: "1px solid #f1f5f9" }}>
                <td style={{ padding: "5px 0", color: "#64748b", fontFamily: "monospace" }}>{k}</td>
                <td style={{ padding: "5px 0", textAlign: "right" }}>{typeof v === "string" ? `"${v}"` : String(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div style={sectionLabel}>Géométrie</div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
          <tbody>
            <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
              <td style={{ padding: "5px 0", color: "#64748b" }}>Type</td>
              <td style={{ padding: "5px 0", textAlign: "right" }}>{selected.feature.geometry.type}</td>
            </tr>
            <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
              <td style={{ padding: "5px 0", color: "#64748b" }}>Vertices</td>
              <td style={{ padding: "5px 0", textAlign: "right", fontFamily: "monospace" }}>{vertexCount}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div style={{ padding: "10px 12px", borderTop: "1px solid #f1f5f9", display: "flex", flexDirection: "column", gap: 6 }}>
        <button onClick={fitMap} style={btnPrimary}>Cadrer la carte sur la feature</button>
        <button onClick={askAgent} style={btnSecondary}>Demander à l'agent…</button>
      </div>
    </div>
  );
}

const sectionLabel: React.CSSProperties = {
  fontSize: 9, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5, margin: "8px 0 4px",
};
const btnPrimary = { background: "#3b82f6", color: "white", border: "none", padding: 7, borderRadius: 5, fontSize: 11, cursor: "pointer" } as const;
const btnSecondary = { background: "white", border: "1px solid #e2e8f0", color: "#0f172a", padding: 7, borderRadius: 5, fontSize: 11, cursor: "pointer" } as const;
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npx vitest run tests/unit/FeatureDrawer.test.tsx
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/Map/FeatureDrawer.tsx frontend/tests/unit/FeatureDrawer.test.tsx
git commit -m "feat(map): add FeatureDrawer with properties, geometry, and ask-agent action"
```

---

## Task 11: Frontend — wire chat widgets in `GeoPage`

Register `useCopilotAction({ name, render })` for `describe_dataset`, `select_features`, and `filter_attributes`. Delete the now-replaced `DatasetCard` (its file was unused but listed in the spec to remove).

**Files:**
- Modify: `frontend/components/GeoPage.tsx`
- Delete: `frontend/components/AgentStateRenderers/DatasetCard.tsx`

- [ ] **Step 1: Make MapView publish its map via a ref**

`onFitMap` needs to call `map.fitBounds(...)` from inside `GeoPage`, which is a parent of `MapView` and so can't use the `useMap()` hook. Add a small ref-prop pattern.

Edit `frontend/components/Map/MapView.tsx`. Change the function signature to accept a ref:

```tsx
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { createContext, MutableRefObject, useContext, useEffect, useRef, useState } from "react";
import { BASEMAP_STYLE_URL } from "@/lib/basemap";

export const MapContext = createContext<maplibregl.Map | null>(null);
export const useMap = () => useContext(MapContext);

interface MapViewProps {
  children?: React.ReactNode;
  mapRef?: MutableRefObject<maplibregl.Map | null>;
}

export function MapView({ children, mapRef }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [map, setMap] = useState<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const m = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP_STYLE_URL,
      center: [-73.6, 45.5],
      zoom: 11,
    });
    m.on("load", () => {
      setMap(m);
      if (mapRef) mapRef.current = m;
    });
    return () => {
      if (mapRef) mapRef.current = null;
      m.remove();
    };
  }, [mapRef]);

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      <MapContext.Provider value={map}>{map && children}</MapContext.Provider>
    </div>
  );
}
```

- [ ] **Step 2: Add the imports and three action registrations to GeoPageBody**

Edit `frontend/components/GeoPage.tsx`. Add to the imports (around line 3):

```tsx
import { ThreadsProvider, useCoAgent, useCoAgentStateRender, useCopilotAction } from "@copilotkit/react-core";
```

Add `useRef` to the React import (around line 5):

```tsx
import { useEffect, useRef, useState } from "react";
```

Add imports for the widget and MapLibre type (around line 13):

```tsx
import maplibregl from "maplibre-gl";
import { MetadataWidget } from "@/components/Widgets/MetadataWidget";
```

Inside `GeoPageBody`, declare a map ref (right after the existing `pushed = useRef(false)` line):

```tsx
  const mapRef = useRef<maplibregl.Map | null>(null);
```

After `useCoAgentStateRender(...)` (around line 125), add the action handlers:

```tsx
  const onShowOnMap = (id: string) => {
    const current = agentState ?? EMPTY_STATE;
    if (current.active_layers.includes(id)) return;
    setAgentState({ ...current, active_layers: [...current.active_layers, id] });
  };

  const onFitMap = (bbox: [number, number, number, number]) => {
    const m = mapRef.current;
    if (!m) return;
    m.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 80, maxZoom: 16 });
  };

  useCopilotAction({
    name: "describe_dataset",
    render: ({ args, result, status }) => {
      if (status === "executing" || !result) {
        return <MetadataWidget data={result as never} datasetId={(args as { id_or_alias?: string })?.id_or_alias ?? ""} status="executing" />;
      }
      return (
        <MetadataWidget
          data={result as never}
          datasetId={(args as { id_or_alias?: string })?.id_or_alias ?? ""}
          status="complete"
          onShowOnMap={onShowOnMap}
          onFitMap={onFitMap}
        />
      );
    },
  });

  useCopilotAction({
    name: "select_features",
    render: ({ result, status }) => {
      if (status === "executing" || !result) {
        return <MetadataWidget data={result as never} datasetId="" status="executing" />;
      }
      const r = result as { dataset_id?: string; meta?: unknown };
      // select_features returns a Command-wrapped payload; unwrap if needed.
      const meta = r.meta ?? r;
      const id = (meta as { id?: string })?.id ?? r.dataset_id ?? "";
      return (
        <MetadataWidget data={meta as never} datasetId={id} status="complete" onShowOnMap={onShowOnMap} onFitMap={onFitMap} />
      );
    },
  });

  useCopilotAction({
    name: "filter_attributes",
    render: ({ result, status }) => {
      if (status === "executing" || !result) {
        return <MetadataWidget data={result as never} datasetId="" status="executing" />;
      }
      const r = result as { dataset_id?: string; meta?: unknown };
      const meta = r.meta ?? r;
      const id = (meta as { id?: string })?.id ?? r.dataset_id ?? "";
      return (
        <MetadataWidget data={meta as never} datasetId={id} status="complete" onShowOnMap={onShowOnMap} onFitMap={onFitMap} />
      );
    },
  });
```

> **Why the loose typing on `result`:** CopilotKit's `useCopilotAction` types the result as `unknown` because the action wasn't declared with parameters here (we're only intercepting render). The widget validates structure at runtime via the data being a `DatasetMeta`-shaped object.

- [ ] **Step 3: Pass the map ref into MapView**

In the JSX (around line 167), update the `<MapView>` opening tag:

```tsx
        <MapView mapRef={mapRef}>
```

- [ ] **Step 4: Delete the obsolete DatasetCard**

```bash
rm frontend/components/AgentStateRenderers/DatasetCard.tsx
```

- [ ] **Step 5: Verify typecheck and unit tests still pass**

```bash
cd frontend && npm run typecheck && npx vitest run
```

Expected: typecheck passes, 12 tests pass (5 MetadataWidget + 3 SchemaWidget + 3 HighlightLayer + 4 FeatureDrawer + 1 existing threadId).

If `useCoAgent` complains about the type of `EMPTY_STATE` after the new code, no other typing change is needed because the new closures only refer to `agentState` and `setAgentState` already in scope.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/GeoPage.tsx frontend/components/Map/MapView.tsx
git rm frontend/components/AgentStateRenderers/DatasetCard.tsx
git commit -m "feat(chat): render MetadataWidget for describe_dataset, select_features, filter_attributes"
```

---

## Task 12: Frontend — wire map widgets

Register click handlers in `MapView`, mount `HighlightLayer` and `FeaturePopup` there, mount `FeatureDrawer` inside `GeoPage`, and dim opacity in `DatasetLayer` when one of its features is selected.

**Files:**
- Modify: `frontend/components/Map/MapView.tsx`
- Modify: `frontend/components/Map/DatasetLayer.tsx`
- Modify: `frontend/components/GeoPage.tsx`

- [ ] **Step 1: Mount the provider in `GeoPage`**

Edit `frontend/components/GeoPage.tsx`. Add to the imports:

```tsx
import { SelectedFeatureProvider } from "@/lib/selectedFeature";
import { FeatureDrawer } from "@/components/Map/FeatureDrawer";
```

Wrap the `MapView` and `DatasetPanel` block in the JSX (around line 167) with the provider, and add `<FeatureDrawer onAskAgent={...} />` inside it. The current return becomes:

```tsx
  return (
    <SelectedFeatureProvider>
      <div style={{ position: "relative", height: "100vh", width: "100vw" }}>
        <MapView>
          {drawing && <DrawTool onPolygon={onPolygon} />}
          {activeLayers.map((id) => (
            <DatasetLayer key={id} datasetId={id} />
          ))}
        </MapView>

        <FeatureDrawer onAskAgent={(prompt) => {
          // Best-effort: focus the chat textarea and pre-fill it.
          const ta = document.querySelector<HTMLTextAreaElement>("textarea[data-copilot-input], .copilotKitInput textarea");
          if (ta) {
            ta.value = prompt;
            ta.focus();
            ta.dispatchEvent(new Event("input", { bubbles: true }));
          }
        }} />

        <DatasetPanel
          datasets={datasets}
          activeLayers={activeLayers}
          onToggle={onToggle}
          onDraw={onDraw}
          drawingActive={drawing}
        />

        <CopilotSidebar
          defaultOpen={true}
          instructions="Demande des analyses spatiales sur les couches WFS de Montréal. Dessine une zone, puis pose ta question."
          labels={{ title: "Géo-agent", initial: "Je peux interroger les couches WFS de Montréal. Dessine une zone et demande." }}
          Header={() => <ChatHeader onNewConversation={onNewConversation} />}
          markdownTagRenderers={markdownTagRenderers}
        />
      </div>
    </SelectedFeatureProvider>
  );
```

- [ ] **Step 2: Mount HighlightLayer and FeaturePopup inside MapView**

Edit `frontend/components/Map/MapView.tsx` (already modified in Task 11 to accept `mapRef`). Add the two imports at the top:

```tsx
import { FeaturePopup } from "./FeaturePopup";
import { HighlightLayer } from "./HighlightLayer";
```

Then update the JSX so both components mount inside the `MapContext.Provider`:

```tsx
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      <MapContext.Provider value={map}>
        {map && (
          <>
            <HighlightLayer />
            <FeaturePopup />
            {children}
          </>
        )}
      </MapContext.Provider>
    </div>
  );
```

- [ ] **Step 3: Add click handlers in `DatasetLayer`**

Edit `frontend/components/Map/DatasetLayer.tsx`. The component must do two things now:

1. Register click handlers on its three layers; on click, fetch the source's features, find the clicked one, set `selected` in context.
2. Read `selected` from context and dim its own paint when a feature **in this dataset** is selected.

Replace the file contents:

```tsx
"use client";

import { useEffect } from "react";
import { useSelectedFeature } from "@/lib/selectedFeature";
import { useMap } from "./MapView";

const DEFAULT_PAINT = {
  fill: { "fill-color": "#3b82f6", "fill-opacity": 0.3, "fill-outline-color": "#1e40af" },
  line: { "line-color": "#ef4444", "line-width": 2 },
  circle: { "circle-radius": 5, "circle-color": "#10b981" },
} as const;

const DIMMED = {
  fill: { "fill-opacity": 0.08 },
  line: { "line-opacity": 0.15 },
  circle: { "circle-opacity": 0.2 },
} as const;

export function DatasetLayer({ datasetId }: { datasetId: string }) {
  const map = useMap();
  const { selected, setSelected } = useSelectedFeature();

  useEffect(() => {
    if (!map) return;
    const sourceId = `ds-${datasetId}`;
    const url = `/api/datasets/${datasetId}`;

    if (!map.getSource(sourceId)) {
      map.addSource(sourceId, { type: "geojson", data: url });
      map.addLayer({ id: `${sourceId}-fill`, source: sourceId, type: "fill", filter: ["==", ["geometry-type"], "Polygon"], paint: DEFAULT_PAINT.fill });
      map.addLayer({ id: `${sourceId}-line`, source: sourceId, type: "line", filter: ["==", ["geometry-type"], "LineString"], paint: DEFAULT_PAINT.line });
      map.addLayer({ id: `${sourceId}-circle`, source: sourceId, type: "circle", filter: ["==", ["geometry-type"], "Point"], paint: DEFAULT_PAINT.circle });
    }

    const layerIds = [`${sourceId}-fill`, `${sourceId}-line`, `${sourceId}-circle`];
    const handler = (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
      const f = e.features?.[0];
      if (!f) return;
      // Resolve the index in the dataset by fetching the GeoJSON once and matching properties+geometry.
      // Cheap shortcut: use the feature directly with index = -1 if we can't resolve.
      const lngLat: [number, number] = [e.lngLat.lng, e.lngLat.lat];
      fetch(url)
        .then((r) => r.json())
        .then((gj: GeoJSON.FeatureCollection) => {
          const idx = gj.features.findIndex((g) => JSON.stringify(g.properties) === JSON.stringify(f.properties));
          const feature = idx >= 0 ? gj.features[idx] : (f as unknown as GeoJSON.Feature);
          setSelected({ datasetId, index: idx, feature, lngLat });
        })
        .catch(() => {
          setSelected({ datasetId, index: -1, feature: f as unknown as GeoJSON.Feature, lngLat });
        });
    };
    for (const lid of layerIds) map.on("click", lid, handler);

    return () => {
      for (const lid of layerIds) {
        map.off("click", lid, handler);
        if (map.getLayer(lid)) map.removeLayer(lid);
      }
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    };
  }, [map, datasetId, setSelected]);

  // Apply dim/restore based on selection.
  useEffect(() => {
    if (!map) return;
    const sourceId = `ds-${datasetId}`;
    const isThisDataset = selected?.datasetId === datasetId;
    const apply = (lid: string, def: Record<string, unknown>, dim: Record<string, unknown>) => {
      if (!map.getLayer(lid)) return;
      const props = isThisDataset ? dim : def;
      for (const [k, v] of Object.entries(props)) {
        map.setPaintProperty(lid, k, v as never);
      }
    };
    apply(`${sourceId}-fill`, DEFAULT_PAINT.fill, DIMMED.fill);
    apply(`${sourceId}-line`, DEFAULT_PAINT.line, DIMMED.line);
    apply(`${sourceId}-circle`, DEFAULT_PAINT.circle, DIMMED.circle);
  }, [map, datasetId, selected]);

  return null;
}
```

> **Note on cursor / hover affordance:** intentionally omitted in v1 — keep the diff focused.

- [ ] **Step 4: Manual verification**

Start the stack (3 terminals: ollama, backend, frontend) and:

1. Draw a polygon → ask the agent to fetch features → click "Afficher sur la carte" if needed
2. Click a rendered feature → popup appears with title + "Détails →"
3. Click "Détails →" → drawer opens, properties + geometry visible, highlight visible (gold)
4. Other features in the same dataset are dimmed (low opacity)
5. Click "Cadrer la carte sur la feature" → map zooms to the feature
6. Click "Demander à l'agent…" → chat textarea has the prefilled prompt

If any step fails, fix it before committing.

- [ ] **Step 5: Run all unit tests and typecheck**

```bash
cd frontend && npm run typecheck && npx vitest run
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/Map/MapView.tsx frontend/components/Map/DatasetLayer.tsx frontend/components/GeoPage.tsx
git commit -m "feat(map): wire feature click handlers, popup, drawer and dim-on-select"
```

---

## Task 13: E2E — feature inspector flow

End-to-end Playwright test that drives the full popup → drawer → highlight cycle. Stubs the dataset endpoints so it doesn't require a real backend.

**Files:**
- Create: `frontend/tests/e2e/feature-inspector.spec.ts`

- [ ] **Step 1: Write the spec**

Create `frontend/tests/e2e/feature-inspector.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

const FAKE_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { id_chaussee: 8421, nom_voie: "Rue Saint-Denis", longueur_m: 147.3, en_service: true },
      geometry: { type: "LineString", coordinates: [[-73.58, 45.52], [-73.57, 45.525], [-73.56, 45.53]] },
    },
  ],
};

const FAKE_META = {
  id: "result_001",
  alias: "test_road",
  feature_count: 1,
  bbox: [-73.58, 45.52, -73.56, 45.53],
  source: { type: "wfs", layer: "geobase:chaussee", filter_summary: "" },
  attribute_schema: { id_chaussee: "number", nom_voie: "string", longueur_m: "number", en_service: "boolean" },
  lineage: { parent_ids: [], operation: "select_features", params: {} },
  created_at: "2026-05-10T12:00:00Z",
  size_bytes: 256,
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/datasets", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([FAKE_META]) }));
  await page.route("**/api/datasets/result_001", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FAKE_GEOJSON) }));
});

test("clicking a feature opens popup, then drawer with properties", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible();

  // Close the chat sidebar so it doesn't intercept clicks.
  await page.evaluate(() => {
    const btn = document.querySelector<HTMLElement>('button[aria-label="Close Chat"]');
    btn?.click();
  });

  // Toggle the dataset on so it becomes an active layer.
  await page.getByRole("checkbox", { name: /test_road/i }).check();

  // Wait for the layer to render.
  await page.waitForFunction(() => {
    const map = (window as unknown as { __map?: maplibregl.Map }).__map;
    return Boolean(map);
  }, { timeout: 5000 }).catch(() => undefined);

  // Click on the canvas in the middle (where the line should be roughly).
  // We dispatch a synthetic click via MapLibre's queryRenderedFeatures path:
  // simpler — fire a JS-level click on the canvas at known coords, then
  // assert the popup text appears.
  const canvas = page.locator("canvas.maplibregl-canvas");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("no canvas bbox");
  await canvas.click({ position: { x: box.width / 2, y: box.height / 2 } });

  // Popup should show the title.
  await expect(page.getByText("Rue Saint-Denis", { exact: false })).toBeVisible({ timeout: 5000 });

  // Click the "Détails →" link inside the popup.
  await page.getByRole("button", { name: /Détails/i }).click();

  // Drawer assertions.
  await expect(page.getByText("FEATURE")).toBeVisible();
  await expect(page.getByText("id_chaussee")).toBeVisible();
  await expect(page.getByText("LineString")).toBeVisible();
  await expect(page.getByRole("button", { name: /Cadrer la carte/i })).toBeVisible();
});
```

> **Why this test is fragile:** synthesizing a click at the centre of the canvas only works if the line actually renders there at the test's zoom level. If the assertion times out, log the canvas dimensions and the source data, then adjust the click coordinates. The test is intentionally minimal — its job is regression coverage on the wiring, not full visual correctness.

- [ ] **Step 2: Expose the map for testability**

Edit `frontend/components/Map/MapView.tsx` (already modified in Tasks 11 and 12). The current `m.on("load", ...)` reads:

```tsx
    m.on("load", () => {
      setMap(m);
      if (mapRef) mapRef.current = m;
    });
```

Update it to also publish the map on `window` outside production builds:

```tsx
    m.on("load", () => {
      setMap(m);
      if (mapRef) mapRef.current = m;
      if (typeof window !== "undefined" && process.env.NODE_ENV !== "production") {
        (window as unknown as { __map: maplibregl.Map }).__map = m;
      }
    });
```

- [ ] **Step 3: Run the e2e test**

Make sure the dev server is running (`npm run dev`).

```bash
cd frontend && npx playwright test feature-inspector.spec.ts
```

If the click misses the line geometry, see the Step-1 note and adjust coordinates.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/e2e/feature-inspector.spec.ts frontend/components/Map/MapView.tsx
git commit -m "test(e2e): cover feature click → popup → drawer flow"
```

---

## Task 14: Final smoke

Run the full suite to make sure nothing else regressed. Includes a manual verification of the chat-widget rendering since the unit tests don't exercise the CopilotKit integration directly.

- [ ] **Step 1: Run all backend tests**

```bash
cd backend && uv run pytest
```

Expected: all green (excluding the `live` marker).

- [ ] **Step 2: Run all frontend unit tests + typecheck**

```bash
cd frontend && npm run typecheck && npx vitest run
```

Expected: all green.

- [ ] **Step 3: Run e2e tests**

```bash
cd frontend && npm run test:e2e
```

Expected: all green (smoke + feature-inspector).

- [ ] **Step 4: Manual chat-widget verification (covered only here)**

Start the stack, open `http://localhost:3000`, draw a zone, ask:

> "Décris-moi le dataset que je viens de dessiner."

Verify the agent calls `describe_dataset` and the chat shows the `MetadataWidget` (badge "DATASET", three tiles, lineage breadcrumb, three buttons). Click "Voir le schéma" — table appears with the three columns. Click `id_chaussee` row — stats subrow loads.

If any of those don't render, the most likely culprit is the action `name` in `useCopilotAction` not matching what the backend tool emits — confirm by inspecting the streamed events in the browser devtools network tab.

- [ ] **Step 5: No commit needed (verification only)**

---

## Notes for the implementer

- **TDD discipline:** every component task starts with a failing test. Don't skip the "verify it fails" step — it confirms the test actually targets the right code path.
- **Don't edit `lib/types.ts`** to add a `DatasetMetaPayload` Zod schema — the widget accepts the runtime shape directly. Adding Zod here is over-engineering for v1.
- **Selection clears the highlight** automatically because `HighlightLayer` reacts to context state. Don't add explicit "clear highlight" calls in popup/drawer close handlers — the context handles it.
- **The "ask agent" prefill is best-effort.** CopilotKit doesn't expose a clean API to set the input. The `document.querySelector` fallback is brittle but acceptable for v1; if/when CopilotKit ships a `useChatInput()` hook, swap it in.
- **Backwards-compat in `DatasetLayer`:** the previous component had no click handler — we replace it wholesale rather than augmenting, which is fine because nothing else depended on its internals.
