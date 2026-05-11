# Tools Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the geo-agent's LangGraph tools into three explicit families (WFS server / local datasets / UI) and add the missing capabilities — local geometry operations (`spatial_overlay`, `transform_geometry`, `spatial_join`), a WFS layer-schema reader (`describe_wfs_layer`), and an agent-driven chat inspector (`inspect_dataset`).

**Architecture:** `backend/geo_agent/agent/tools/` becomes three subpackages (`wfs/`, `datasets/`, `ui/`); a new `tools/__init__.py` re-exports every tool and an `ALL_TOOLS` list that `graph.py` consumes. A new `backend/geo_agent/services/geometry_ops.py` holds pure GeoPandas/Shapely functions (GeoJSON dict → GeoJSON dict). New tools follow the established `@tool` + Pydantic-typed-params + `Command`/`dict` return convention. Three new inline chat widgets render `inspect_dataset` results via CopilotKit's per-tool `render` hook. The `SYSTEM_PROMPT` tool catalog is rewritten to mirror the three families.

**Tech Stack:** Python 3.12, pydantic v2, langchain_core.tools, langgraph, geopandas 1.x, shapely 2.x, pyproj, pytest. Frontend: Next.js 16, React 19, CopilotKit 1.5, Vitest, TypeScript.

**Decisions locked in (from the design spec `docs/superpowers/specs/2026-05-11-tools-revision-design.md`):**
- Consolidated verbs: one `spatial_overlay(op=...)`, one `transform_geometry(op=...)`, one `inspect_dataset(view=...)` — 13 tools total.
- Metric operations (`buffer`) reproject to EPSG:32188 (NAD83 / MTM zone 8) and back to EPSG:4326.
- `spatial_overlay` `intersection`/`clip` use `geopandas.clip` (keeps left's attributes, drops non-overlapping features). `union`/`difference` use `geopandas.overlay`.
- `spatial_join` does a **left** join, suffixes **all** right columns with `_r`, keeps the first match per left feature.
- `inspect_dataset` returns feature *properties* only — never coordinates.
- Existing 7 carried-over tools change file location only; behaviour unchanged. No backward-compat shims.
- Backend unit tests only; frontend Vitest only; E2E is optional.

---

## File Structure

**New files:**
- `backend/geo_agent/agent/tools/__init__.py` — (currently empty) becomes the re-export hub + `ALL_TOOLS`
- `backend/geo_agent/agent/tools/wfs/__init__.py` — empty package marker
- `backend/geo_agent/agent/tools/wfs/describe_layer.py` — `describe_wfs_layer` tool
- `backend/geo_agent/agent/tools/datasets/__init__.py` — empty package marker
- `backend/geo_agent/agent/tools/datasets/spatial_overlay.py` — `spatial_overlay` tool
- `backend/geo_agent/agent/tools/datasets/transform_geometry.py` — `transform_geometry` tool
- `backend/geo_agent/agent/tools/datasets/spatial_join.py` — `spatial_join` tool
- `backend/geo_agent/agent/tools/ui/__init__.py` — empty package marker
- `backend/geo_agent/agent/tools/ui/inspect_dataset.py` — `inspect_dataset` tool
- `backend/geo_agent/services/geometry_ops.py` — pure GeoPandas/Shapely functions
- `backend/tests/unit/test_tools_package.py` — guard test for the `tools/__init__` re-export
- `backend/tests/unit/test_geometry_ops.py` — unit tests for `geometry_ops`
- `backend/tests/unit/test_tool_spatial_overlay.py`
- `backend/tests/unit/test_tool_transform_geometry.py`
- `backend/tests/unit/test_tool_spatial_join.py`
- `backend/tests/unit/test_tool_describe_wfs_layer.py`
- `backend/tests/unit/test_tool_inspect_dataset.py`
- `frontend/components/Widgets/FeatureWidget.tsx`
- `frontend/components/Widgets/FeatureListWidget.tsx`
- `frontend/components/Widgets/InspectDatasetWidget.tsx`
- `frontend/tests/unit/FeatureWidget.test.tsx`
- `frontend/tests/unit/FeatureListWidget.test.tsx`
- `frontend/tests/unit/InspectDatasetWidget.test.tsx`

**Moved files (via `git mv`, contents unchanged unless noted):**
- `tools/list_wfs_layers.py` → `tools/wfs/list_layers.py`
- `tools/select_features.py` → `tools/wfs/select_features.py`
- `tools/filter_attributes.py` → `tools/datasets/filter_attributes.py`
- `tools/aggregate.py` → `tools/datasets/aggregate.py`
- `tools/describe_dataset.py` → `tools/datasets/describe_dataset.py`
- `tools/list_datasets.py` → `tools/datasets/list_datasets.py`
- `tools/show_on_map.py` → `tools/ui/show_on_map.py`

**Modified files:**
- `backend/geo_agent/agent/graph.py` — import `ALL_TOOLS` from `geo_agent.agent.tools`
- `backend/geo_agent/agent/error_helpers.py` — add `dataset_not_found_command` helper
- `backend/geo_agent/agent/prompts.py` — rewrite the `# Tool catalog` section + add core rules + `empty_result`
- `backend/tests/unit/test_tool_list_wfs_layers.py`, `test_tool_select_features.py`, `test_tool_filter_attributes.py`, `test_tool_aggregate.py`, `test_tool_describe_and_list.py`, `test_tool_show_on_map.py` — update import paths and monkeypatch target strings
- `backend/tests/unit/test_prompt_builder.py` — add assertions for the new prompt content
- `frontend/components/Widgets/SchemaWidget.tsx` — add optional `sample` prop (skip the fetch when provided)
- `frontend/components/GeoPage.tsx` — register the `inspect_dataset` `useCopilotAction` renderer
- `frontend/lib/types.ts` — add the `inspect_dataset` payload zod schemas / types

---

## Task 1: Reorganize `tools/` into `wfs/`, `datasets/`, `ui/` subpackages

**Files:**
- Create: `backend/geo_agent/agent/tools/wfs/__init__.py`, `backend/geo_agent/agent/tools/datasets/__init__.py`, `backend/geo_agent/agent/tools/ui/__init__.py` (all empty)
- Move: the 7 tool files listed in **File Structure**
- Modify: `backend/geo_agent/agent/tools/__init__.py`, `backend/geo_agent/agent/graph.py`, and 6 `backend/tests/unit/test_tool_*.py` files
- Test: `backend/tests/unit/test_tools_package.py` (new)

- [ ] **Step 1: Create the three subpackage directories and empty `__init__.py` files**

```bash
cd backend
mkdir -p geo_agent/agent/tools/wfs geo_agent/agent/tools/datasets geo_agent/agent/tools/ui
touch geo_agent/agent/tools/wfs/__init__.py geo_agent/agent/tools/datasets/__init__.py geo_agent/agent/tools/ui/__init__.py
```

- [ ] **Step 2: Move the seven tool files with `git mv`**

```bash
cd backend
git mv geo_agent/agent/tools/list_wfs_layers.py  geo_agent/agent/tools/wfs/list_layers.py
git mv geo_agent/agent/tools/select_features.py  geo_agent/agent/tools/wfs/select_features.py
git mv geo_agent/agent/tools/filter_attributes.py geo_agent/agent/tools/datasets/filter_attributes.py
git mv geo_agent/agent/tools/aggregate.py         geo_agent/agent/tools/datasets/aggregate.py
git mv geo_agent/agent/tools/describe_dataset.py  geo_agent/agent/tools/datasets/describe_dataset.py
git mv geo_agent/agent/tools/list_datasets.py     geo_agent/agent/tools/datasets/list_datasets.py
git mv geo_agent/agent/tools/show_on_map.py       geo_agent/agent/tools/ui/show_on_map.py
```

The moved files' internal imports are all absolute (`geo_agent.agent.error_helpers`, `geo_agent.agent.registry`, `geo_agent.models`, `geo_agent.services.*`) — nothing inside them needs to change.

- [ ] **Step 3: Write `tools/__init__.py` as the re-export hub**

Replace the (empty) `backend/geo_agent/agent/tools/__init__.py` with:

```python
from geo_agent.agent.tools.datasets.aggregate import aggregate
from geo_agent.agent.tools.datasets.describe_dataset import describe_dataset
from geo_agent.agent.tools.datasets.filter_attributes import filter_attributes
from geo_agent.agent.tools.datasets.list_datasets import list_datasets
from geo_agent.agent.tools.ui.show_on_map import hide_on_map, show_on_map
from geo_agent.agent.tools.wfs.list_layers import list_wfs_layers
from geo_agent.agent.tools.wfs.select_features import select_features

# Each new-tool task below appends its import + entry to ALL_TOOLS.
ALL_TOOLS = [
    # WFS server tools
    list_wfs_layers,
    select_features,
    # Local dataset tools
    filter_attributes,
    aggregate,
    describe_dataset,
    list_datasets,
    # UI tools
    show_on_map,
    hide_on_map,
]

__all__ = [
    "ALL_TOOLS",
    "list_wfs_layers",
    "select_features",
    "filter_attributes",
    "aggregate",
    "describe_dataset",
    "list_datasets",
    "show_on_map",
    "hide_on_map",
]
```

- [ ] **Step 4: Point `graph.py` at `ALL_TOOLS`**

Edit `backend/geo_agent/agent/graph.py`: delete the eight `from geo_agent.agent.tools.<name> import ...` lines and the literal `TOOLS = [ ... ]` block, and replace them with:

```python
from geo_agent.agent.tools import ALL_TOOLS

TOOLS = ALL_TOOLS
```

Leave the rest of `graph.py` (`_build_llm`, `build_agent`) unchanged.

- [ ] **Step 5: Update the six existing tool test files' import paths and monkeypatch strings**

Apply these exact substitutions:

`backend/tests/unit/test_tool_list_wfs_layers.py`:
- `from geo_agent.agent.tools.list_wfs_layers import list_wfs_layers` → `from geo_agent.agent.tools.wfs.list_layers import list_wfs_layers`
- both occurrences of `"geo_agent.agent.tools.list_wfs_layers.get_services"` → `"geo_agent.agent.tools.wfs.list_layers.get_services"`

`backend/tests/unit/test_tool_select_features.py`:
- `from geo_agent.agent.tools.select_features import DatasetSource, PolygonSource, select_features` → `from geo_agent.agent.tools.wfs.select_features import DatasetSource, PolygonSource, select_features`
- inside `test_select_features_with_attribute_filter_reaches_wfs`: `from geo_agent.agent.tools.select_features import AttributeFilterInput, PolygonSource` → `from geo_agent.agent.tools.wfs.select_features import AttributeFilterInput, PolygonSource`
- `monkeypatch.setattr("geo_agent.agent.tools.select_features.get_services", lambda: services)` → `monkeypatch.setattr("geo_agent.agent.tools.wfs.select_features.get_services", lambda: services)`

`backend/tests/unit/test_tool_filter_attributes.py`:
- `from geo_agent.agent.tools.filter_attributes import filter_attributes` → `from geo_agent.agent.tools.datasets.filter_attributes import filter_attributes`
- `monkeypatch.setattr("geo_agent.agent.tools.filter_attributes.get_services", lambda: services)` → `monkeypatch.setattr("geo_agent.agent.tools.datasets.filter_attributes.get_services", lambda: services)`

`backend/tests/unit/test_tool_aggregate.py`:
- `from geo_agent.agent.tools.aggregate import aggregate as aggregate_tool` → `from geo_agent.agent.tools.datasets.aggregate import aggregate as aggregate_tool`
- `monkeypatch.setattr("geo_agent.agent.tools.aggregate.get_services", lambda: services)` → `monkeypatch.setattr("geo_agent.agent.tools.datasets.aggregate.get_services", lambda: services)`

`backend/tests/unit/test_tool_describe_and_list.py`:
- `from geo_agent.agent.tools.describe_dataset import describe_dataset` → `from geo_agent.agent.tools.datasets.describe_dataset import describe_dataset`
- `from geo_agent.agent.tools.list_datasets import list_datasets` → `from geo_agent.agent.tools.datasets.list_datasets import list_datasets`
- `monkeypatch.setattr(f"geo_agent.agent.tools.{mod}.get_services", lambda: services)` → `monkeypatch.setattr(f"geo_agent.agent.tools.datasets.{mod}.get_services", lambda: services)`

`backend/tests/unit/test_tool_show_on_map.py`:
- `from geo_agent.agent.tools.show_on_map import hide_on_map, show_on_map` → `from geo_agent.agent.tools.ui.show_on_map import hide_on_map, show_on_map`
- `monkeypatch.setattr("geo_agent.agent.tools.show_on_map.get_services", lambda: services)` → `monkeypatch.setattr("geo_agent.agent.tools.ui.show_on_map.get_services", lambda: services)`

- [ ] **Step 6: Add the package guard test**

Create `backend/tests/unit/test_tools_package.py`:

```python
def test_all_tools_re_exported_and_named() -> None:
    from geo_agent.agent.tools import ALL_TOOLS

    names = {t.name for t in ALL_TOOLS}
    expected = {
        "list_wfs_layers",
        "select_features",
        "filter_attributes",
        "aggregate",
        "describe_dataset",
        "list_datasets",
        "show_on_map",
        "hide_on_map",
    }
    assert expected.issubset(names)


def test_graph_uses_all_tools() -> None:
    from geo_agent.agent.graph import TOOLS
    from geo_agent.agent.tools import ALL_TOOLS

    assert TOOLS is ALL_TOOLS
```

- [ ] **Step 7: Run the whole backend suite**

Run: `cd backend && uv run pytest -q`
Expected: 0 failures (all tests pass with the new import paths).

- [ ] **Step 8: Lint**

Run: `cd backend && uv run ruff check geo_agent tests`
Expected: clean. (If ruff complains about import sorting in `tools/__init__.py`, run `uv run ruff check --fix geo_agent tests` and re-run.)

- [ ] **Step 9: Commit**

```bash
cd backend
git add -A
git commit -m "refactor(tools): split into wfs/datasets/ui subpackages with ALL_TOOLS re-export"
```

---

## Task 2: `geometry_ops.overlay()`

**Files:**
- Create: `backend/geo_agent/services/geometry_ops.py`
- Test: `backend/tests/unit/test_geometry_ops.py` (new)

- [ ] **Step 1: Write the failing tests for `overlay`**

Create `backend/tests/unit/test_geometry_ops.py`:

```python
import pytest
from shapely.geometry import shape

from geo_agent.services.geometry_ops import overlay


def _poly(coords: list, **props) -> dict:
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coords]}, "properties": props}


def _fc(*features: dict) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}


def test_overlay_intersection_clips_left_to_right_and_keeps_left_attrs() -> None:
    lines = _fc(
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [10, 0]]}, "properties": {"name": "rue A"}},
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 5], [10, 5]]}, "properties": {"name": "rue B"}},
    )
    box = _fc(_poly([[2, -1], [4, -1], [4, 1], [2, 1], [2, -1]], zone="z1"))

    out = overlay(lines, box, "intersection")

    assert len(out["features"]) == 1
    f = out["features"][0]
    assert f["properties"]["name"] == "rue A"
    xs = [c[0] for c in f["geometry"]["coordinates"]]
    assert min(xs) >= 1.999 and max(xs) <= 4.001


def test_overlay_clip_is_same_as_intersection() -> None:
    lines = _fc({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [10, 0]]}, "properties": {"name": "rue A"}})
    box = _fc(_poly([[2, -1], [4, -1], [4, 1], [2, 1], [2, -1]]))
    assert overlay(lines, box, "clip") == overlay(lines, box, "intersection")


def test_overlay_difference_removes_overlapping_part() -> None:
    a = _fc(_poly([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], id=1))
    b = _fc(_poly([[0, 0], [5, 0], [5, 10], [0, 10], [0, 0]], id=2))

    out = overlay(a, b, "difference")

    assert len(out["features"]) == 1
    assert abs(shape(out["features"][0]["geometry"]).area - 50.0) < 0.01


def test_overlay_intersection_empty_when_disjoint() -> None:
    a = _fc(_poly([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]))
    b = _fc(_poly([[100, 100], [101, 100], [101, 101], [100, 101], [100, 100]]))
    assert overlay(a, b, "intersection")["features"] == []


def test_overlay_empty_when_either_side_empty() -> None:
    a = _fc(_poly([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]))
    empty = _fc()
    assert overlay(a, empty, "intersection")["features"] == []
    assert overlay(empty, a, "union")["features"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_geometry_ops.py -v`
Expected: FAIL — `ModuleNotFoundError: geo_agent.services.geometry_ops`.

- [ ] **Step 3: Create `geometry_ops.py` with `overlay` (and the shared helpers)**

Create `backend/geo_agent/services/geometry_ops.py`:

```python
from __future__ import annotations

import json
import math
from typing import Any, Literal

import geopandas as gpd

WGS84 = "EPSG:4326"
MONTREAL_METRIC_CRS = "EPSG:32188"  # NAD83 / MTM zone 8 — Montreal's metric reference

OverlayOp = Literal["intersection", "union", "difference", "clip"]
TransformOp = Literal["buffer", "centroid", "simplify", "dissolve"]
JoinPredicate = Literal["intersects", "within", "contains"]


def _to_gdf(geojson: dict) -> gpd.GeoDataFrame:
    feats = geojson.get("features", [])
    if not feats:
        return gpd.GeoDataFrame(geometry=[], crs=WGS84)
    return gpd.GeoDataFrame.from_features(feats, crs=WGS84)


def _clean(obj: Any) -> Any:
    """Replace NaN floats (introduced by left joins / overlays) with None and strip
    numpy scalars so the result is plain JSON-safe Python."""
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def _to_geojson(gdf: gpd.GeoDataFrame) -> dict:
    if len(gdf) == 0:
        return {"type": "FeatureCollection", "features": []}
    return _clean(json.loads(gdf.to_json()))


def overlay(left: dict, right: dict, op: OverlayOp) -> dict:
    """Geometric overlay of two feature collections, returning a new collection.

    intersection / clip — parts of `left` that fall inside `right` (keeps left's attributes,
                          drops features that do not overlap).
    union               — geometric union of both layers' features (attributes from both).
    difference          — `left` minus the parts overlapping `right` (keeps left's attributes).
    """
    left_gdf = _to_gdf(left)
    right_gdf = _to_gdf(right)
    if len(left_gdf) == 0 or len(right_gdf) == 0:
        return {"type": "FeatureCollection", "features": []}
    if op in ("intersection", "clip"):
        out = gpd.clip(left_gdf, right_gdf, keep_geom_type=False)
    elif op in ("union", "difference"):
        out = gpd.overlay(left_gdf, right_gdf, how=op, keep_geom_type=False)
    else:
        raise ValueError(f"unknown overlay op: {op!r}")
    return _to_geojson(out)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_geometry_ops.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd backend
git add geo_agent/services/geometry_ops.py tests/unit/test_geometry_ops.py
git commit -m "feat(geometry_ops): add overlay (intersection/clip/union/difference)"
```

---

## Task 3: `geometry_ops.transform()`

**Files:**
- Modify: `backend/geo_agent/services/geometry_ops.py`
- Test: `backend/tests/unit/test_geometry_ops.py` (append)

- [ ] **Step 1: Append the failing tests for `transform`**

Append to `backend/tests/unit/test_geometry_ops.py`:

```python
from geo_agent.services.geometry_ops import transform


def test_transform_buffer_produces_polygon_with_area_and_keeps_attrs() -> None:
    pt = _fc({"type": "Feature", "geometry": {"type": "Point", "coordinates": [-73.567, 45.501]}, "properties": {"name": "x"}})
    out = transform(pt, "buffer", distance_meters=100)
    geom = shape(out["features"][0]["geometry"])
    assert geom.geom_type == "Polygon"
    assert geom.area > 0
    assert out["features"][0]["properties"]["name"] == "x"


def test_transform_buffer_requires_distance() -> None:
    pt = _fc({"type": "Feature", "geometry": {"type": "Point", "coordinates": [-73.567, 45.501]}, "properties": {}})
    with pytest.raises(ValueError):
        transform(pt, "buffer")


def test_transform_centroid_is_point() -> None:
    poly = _fc(_poly([[-73.6, 45.5], [-73.5, 45.5], [-73.5, 45.6], [-73.6, 45.6], [-73.6, 45.5]], k=1))
    out = transform(poly, "centroid")
    assert out["features"][0]["geometry"]["type"] == "Point"
    assert out["features"][0]["properties"]["k"] == 1


def test_transform_simplify_reduces_vertices() -> None:
    line = _fc({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 0.0000001], [2, 0]]}, "properties": {}})
    out = transform(line, "simplify", tolerance=0.001)
    assert len(out["features"][0]["geometry"]["coordinates"]) == 2


def test_transform_simplify_requires_tolerance() -> None:
    line = _fc({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 0], [2, 0]]}, "properties": {}})
    with pytest.raises(ValueError):
        transform(line, "simplify")


def test_transform_dissolve_by_attribute_collapses_per_key() -> None:
    fc = _fc(
        _poly([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]], cat="a"),
        _poly([[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]], cat="a"),
        _poly([[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]], cat="b"),
    )
    out = transform(fc, "dissolve", by="cat")
    assert len(out["features"]) == 2
    assert sorted(f["properties"]["cat"] for f in out["features"]) == ["a", "b"]


def test_transform_dissolve_without_by_makes_one_feature() -> None:
    fc = _fc(
        _poly([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]], cat="a"),
        _poly([[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]], cat="b"),
    )
    out = transform(fc, "dissolve")
    assert len(out["features"]) == 1


def test_transform_dissolve_unknown_attribute_raises() -> None:
    fc = _fc(_poly([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]], cat="a"))
    with pytest.raises(ValueError):
        transform(fc, "dissolve", by="nope")
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_geometry_ops.py -v -k transform`
Expected: FAIL — `ImportError: cannot import name 'transform'`.

- [ ] **Step 3: Add `transform` to `geometry_ops.py`**

Append to `backend/geo_agent/services/geometry_ops.py`:

```python
def transform(
    geojson: dict,
    op: TransformOp,
    *,
    distance_meters: float | None = None,
    tolerance: float | None = None,
    by: str | None = None,
) -> dict:
    """Single-dataset geometry transformation, returning a new collection.

    buffer    — requires distance_meters (metres); reprojects to EPSG:32188, buffers, reprojects back.
    centroid  — replaces each geometry with its centroid (Point); attributes preserved.
    simplify  — requires tolerance (degrees, since the data is EPSG:4326); Douglas–Peucker.
    dissolve  — merge features; with `by` (attribute name), one feature per distinct value of that
                attribute keeping only that attribute; without `by`, one feature with no attributes.
    """
    gdf = _to_gdf(geojson)
    if len(gdf) == 0:
        return {"type": "FeatureCollection", "features": []}

    if op == "buffer":
        if distance_meters is None:
            raise ValueError("buffer requires distance_meters")
        metric = gdf.to_crs(MONTREAL_METRIC_CRS)
        metric["geometry"] = metric.geometry.buffer(distance_meters)
        out = metric.to_crs(WGS84)
    elif op == "centroid":
        metric = gdf.to_crs(MONTREAL_METRIC_CRS)
        metric["geometry"] = metric.geometry.centroid
        out = metric.to_crs(WGS84)
    elif op == "simplify":
        if tolerance is None:
            raise ValueError("simplify requires tolerance")
        out = gdf.copy()
        out["geometry"] = gdf.geometry.simplify(tolerance, preserve_topology=True)
    elif op == "dissolve":
        if by is None:
            out = gdf[["geometry"]].dissolve().reset_index(drop=True)
        else:
            if by not in gdf.columns:
                raise ValueError(f"dissolve: attribute {by!r} not in dataset")
            out = gdf[[by, "geometry"]].dissolve(by=by).reset_index()
    else:
        raise ValueError(f"unknown transform op: {op!r}")

    return _to_geojson(out)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_geometry_ops.py -v`
Expected: PASS (all `overlay` and `transform` tests).

- [ ] **Step 5: Commit**

```bash
cd backend
git add geo_agent/services/geometry_ops.py tests/unit/test_geometry_ops.py
git commit -m "feat(geometry_ops): add transform (buffer/centroid/simplify/dissolve)"
```

---

## Task 4: `geometry_ops.spatial_join()`

**Files:**
- Modify: `backend/geo_agent/services/geometry_ops.py`
- Test: `backend/tests/unit/test_geometry_ops.py` (append)

- [ ] **Step 1: Append the failing tests for `spatial_join`**

Append to `backend/tests/unit/test_geometry_ops.py`:

```python
from geo_agent.services.geometry_ops import spatial_join


def _pt(x: float, y: float, **props) -> dict:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, y]}, "properties": props}


def test_spatial_join_attaches_right_attributes_and_keeps_all_left() -> None:
    pts = _fc(_pt(1, 1, id="p1"), _pt(9, 9, id="p2"))
    zones = _fc(_poly([[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]], zone="A"))

    out = spatial_join(pts, zones, "within")

    by_id = {f["properties"]["id"]: f["properties"] for f in out["features"]}
    assert len(out["features"]) == 2
    assert by_id["p1"]["zone_r"] == "A"
    assert by_id["p2"]["zone_r"] is None


def test_spatial_join_suffixes_colliding_columns_with_r() -> None:
    pts = _fc(_pt(1, 1, name="left"))
    zones = _fc(_poly([[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]], name="right"))

    out = spatial_join(pts, zones, "within")

    props = out["features"][0]["properties"]
    assert props["name"] == "left"
    assert props["name_r"] == "right"


def test_spatial_join_first_match_wins() -> None:
    pts = _fc(_pt(1, 1, id="p1"))
    zones = _fc(
        _poly([[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]], zone="A"),
        _poly([[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]], zone="B"),  # overlapping second zone
    )

    out = spatial_join(pts, zones, "within")

    assert len(out["features"]) == 1
    assert out["features"][0]["properties"]["zone_r"] in ("A", "B")


def test_spatial_join_empty_left_returns_empty() -> None:
    zones = _fc(_poly([[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]], zone="A"))
    assert spatial_join(_fc(), zones, "within")["features"] == []
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_geometry_ops.py -v -k spatial_join`
Expected: FAIL — `ImportError: cannot import name 'spatial_join'`.

- [ ] **Step 3: Add `spatial_join` to `geometry_ops.py`**

Append to `backend/geo_agent/services/geometry_ops.py`:

```python
def spatial_join(left: dict, right: dict, predicate: JoinPredicate) -> dict:
    """Left spatial join: every feature of `left`, with `right`'s attributes attached when
    the spatial `predicate` holds (otherwise null). All right columns are suffixed `_r`. When a
    left feature matches several right features, the first match wins. Geometry stays `left`'s.
    """
    left_gdf = _to_gdf(left)
    if len(left_gdf) == 0:
        return {"type": "FeatureCollection", "features": []}
    right_gdf = _to_gdf(right)
    if len(right_gdf) == 0:
        return _to_geojson(left_gdf)

    right_renamed = right_gdf.rename(columns={c: f"{c}_r" for c in right_gdf.columns if c != "geometry"})
    joined = gpd.sjoin(left_gdf, right_renamed, how="left", predicate=predicate)
    joined = joined.drop(columns=[c for c in ("index_right", "index_left") if c in joined.columns])
    joined = joined.loc[~joined.index.duplicated(keep="first")]
    return _to_geojson(joined)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_geometry_ops.py -v`
Expected: PASS (all `geometry_ops` tests).

- [ ] **Step 5: Commit**

```bash
cd backend
git add geo_agent/services/geometry_ops.py tests/unit/test_geometry_ops.py
git commit -m "feat(geometry_ops): add spatial_join (left join, _r suffix, first match)"
```

---

## Task 5: `dataset_not_found_command` helper

**Files:**
- Modify: `backend/geo_agent/agent/error_helpers.py`
- Test: `backend/tests/unit/test_error_helpers.py` (new)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_error_helpers.py`:

```python
from types import SimpleNamespace

from geo_agent.agent.error_helpers import dataset_not_found_command


class _FakeStore:
    def list(self):
        return [SimpleNamespace(id="result_001"), SimpleNamespace(id="result_002")]


class _EmptyStore:
    def list(self):
        return []


def test_dataset_not_found_command_lists_known_ids() -> None:
    cmd = dataset_not_found_command(_FakeStore(), "result_999", "t")
    err = cmd.update["errors"][0]
    assert err["code"] == "dataset_not_found"
    assert "result_001" in err["suggestion"] and "result_002" in err["suggestion"]
    assert cmd.update["messages"][0].tool_call_id == "t"


def test_dataset_not_found_command_handles_empty_store() -> None:
    cmd = dataset_not_found_command(_EmptyStore(), "result_999", "t")
    assert cmd.update["errors"][0]["suggestion"] == "Available IDs: (none)"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_error_helpers.py -v`
Expected: FAIL — `ImportError: cannot import name 'dataset_not_found_command'`.

- [ ] **Step 3: Add the helper to `error_helpers.py`**

Add to `backend/geo_agent/agent/error_helpers.py` (after `tool_error_command`, keeping the existing imports plus a new one for the store Protocol):

```python
from geo_agent.services.result_store import ResultStore  # add to the import block at the top
```

```python
def dataset_not_found_command(store: ResultStore, dataset_id: str, tool_call_id: str) -> Command:
    """Standard `dataset_not_found` error: lists the available dataset ids in the suggestion."""
    known = [m.id for m in store.list()]
    return tool_error_command(
        ToolError(
            code="dataset_not_found",
            message=f"No dataset {dataset_id}",
            suggestion=f"Available IDs: {', '.join(known) if known else '(none)'}",
        ),
        tool_call_id,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/test_error_helpers.py -v`
Expected: PASS.

- [ ] **Step 5: Run the whole suite (no regressions from the new import)**

Run: `cd backend && uv run pytest -q`
Expected: 0 failures.

- [ ] **Step 6: Commit**

```bash
cd backend
git add geo_agent/agent/error_helpers.py tests/unit/test_error_helpers.py
git commit -m "feat(error_helpers): add dataset_not_found_command helper"
```

---

## Task 6: `spatial_overlay` tool

**Files:**
- Create: `backend/geo_agent/agent/tools/datasets/spatial_overlay.py`
- Modify: `backend/geo_agent/agent/tools/__init__.py`
- Test: `backend/tests/unit/test_tool_spatial_overlay.py` (new), `backend/tests/unit/test_tools_package.py` (append)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_tool_spatial_overlay.py`:

```python
from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.spatial_overlay import spatial_overlay
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.spatial_overlay.get_services", lambda: services)
    return services


def _put_poly(services: Services, coords: list, alias: str | None = None) -> str:
    return services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coords]}, "properties": {"k": 1}}]},
        {"alias": alias, "source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


async def test_spatial_overlay_intersection_creates_dataset_with_two_parents(services: Services) -> None:
    left = _put_poly(services, [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], alias="a")
    right = _put_poly(services, [[5, 5], [15, 5], [15, 15], [5, 15], [5, 5]], alias="b")

    r = await spatial_overlay.coroutine(left_id=left, right_id=right, op="intersection", alias="overlap", tool_call_id="t", state={"datasets": []})

    meta_lite = r.update["datasets"][0]
    assert meta_lite["alias"] == "overlap"
    assert meta_lite["feature_count"] == 1
    meta = services.store.get_meta(meta_lite["id"])
    assert meta.lineage.parent_ids == [left, right]
    assert meta.lineage.operation == "spatial_overlay"
    assert meta.lineage.params == {"op": "intersection"}


async def test_spatial_overlay_unknown_left_returns_error(services: Services) -> None:
    right = _put_poly(services, [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]])
    r = await spatial_overlay.coroutine(left_id="result_999", right_id=right, op="intersection", alias=None, tool_call_id="t", state={"datasets": []})
    assert r.update["errors"][0]["code"] == "dataset_not_found"


async def test_spatial_overlay_empty_result_when_disjoint(services: Services) -> None:
    left = _put_poly(services, [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]])
    right = _put_poly(services, [[100, 100], [101, 100], [101, 101], [100, 101], [100, 100]])
    r = await spatial_overlay.coroutine(left_id=left, right_id=right, op="intersection", alias=None, tool_call_id="t", state={"datasets": []})
    assert r.update["errors"][0]["code"] == "empty_result"


async def test_spatial_overlay_args_schema_rejects_unknown_op() -> None:
    from pydantic import ValidationError

    schema = spatial_overlay.args_schema
    with pytest.raises(ValidationError):
        schema.model_validate({"left_id": "result_001", "right_id": "result_002", "op": "banana", "tool_call_id": "t", "state": {}})
```

Append to `backend/tests/unit/test_tools_package.py` inside `test_all_tools_re_exported_and_named`'s `expected` set: add `"spatial_overlay"`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_tool_spatial_overlay.py -v`
Expected: FAIL — `ModuleNotFoundError: geo_agent.agent.tools.datasets.spatial_overlay`.

- [ ] **Step 3: Create the tool**

Create `backend/geo_agent/agent/tools/datasets/spatial_overlay.py`:

```python
from typing import Annotated, Literal

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import Field

from geo_agent.agent.error_helpers import (
    dataset_created_command,
    dataset_not_found_command,
    tool_error_command,
)
from geo_agent.agent.registry import get_services
from geo_agent.models import DatasetMetaLite, ToolError
from geo_agent.services.geometry_ops import overlay as do_overlay


def _meta_lite(meta) -> DatasetMetaLite:
    return DatasetMetaLite(
        id=meta.id,
        alias=meta.alias,
        feature_count=meta.feature_count,
        bbox=meta.bbox,
        layer=meta.source.layer,
        operation=meta.lineage.operation,
    )


@tool
async def spatial_overlay(
    left_id: str,
    right_id: str,
    op: Literal["intersection", "union", "difference", "clip"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    alias: Annotated[str | None, Field(description="Short, descriptive name for the new dataset")] = None,
) -> Command:
    """Combine two datasets geometrically, producing a new dataset.

    op:
      "intersection" / "clip" — keep only the parts of `left` that fall inside `right`
                                (keeps left's attributes; non-overlapping features are dropped)
      "union"                 — geometric union of both layers' features (attributes from both)
      "difference"            — `left` minus the parts overlapping `right` (keeps left's attributes)

    Example — streets clipped to a zone:
      {"left_id": "result_003", "right_id": "result_001", "op": "intersection", "alias": "rues_dans_zone"}

    On failure: dataset_not_found (bad left_id/right_id), empty_result (left and right do not overlap).
    """
    services = get_services()
    try:
        left_gj = services.store.get_geojson(left_id)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, left_id, tool_call_id)
    try:
        right_gj = services.store.get_geojson(right_id)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, right_id, tool_call_id)

    out = do_overlay(left_gj, right_gj, op)
    if not out.get("features"):
        return tool_error_command(
            ToolError(
                code="empty_result",
                message=f"{op}({left_id}, {right_id}) produced no features",
                suggestion="left and right may not overlap; check the inputs or try a different op",
            ),
            tool_call_id,
        )

    rid = services.store.put(
        out,
        {
            "alias": alias,
            "source": {"type": "derived", "filter_summary": f"{op}({left_id}, {right_id})"},
            "lineage": {"parent_ids": [left_id, right_id], "operation": "spatial_overlay", "params": {"op": op}},
        },
    )
    meta = services.store.get_meta(rid)
    return dataset_created_command(
        _meta_lite(meta),
        tool_result={"dataset_id": rid, "alias": meta.alias, "feature_count": meta.feature_count, "bbox": list(meta.bbox)},
        state=state,
        tool_call_id=tool_call_id,
    )
```

- [ ] **Step 4: Register the tool in `tools/__init__.py`**

Edit `backend/geo_agent/agent/tools/__init__.py`: add `from geo_agent.agent.tools.datasets.spatial_overlay import spatial_overlay` to the import block, add `spatial_overlay` to the `ALL_TOOLS` list (in the "Local dataset tools" group), and add `"spatial_overlay"` to `__all__`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_tool_spatial_overlay.py tests/unit/test_tools_package.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd backend
git add geo_agent/agent/tools/datasets/spatial_overlay.py geo_agent/agent/tools/__init__.py tests/unit/test_tool_spatial_overlay.py tests/unit/test_tools_package.py
git commit -m "feat(tools): add spatial_overlay (intersection/union/difference/clip)"
```

---

## Task 7: `transform_geometry` tool

**Files:**
- Create: `backend/geo_agent/agent/tools/datasets/transform_geometry.py`
- Modify: `backend/geo_agent/agent/tools/__init__.py`
- Test: `backend/tests/unit/test_tool_transform_geometry.py` (new), `backend/tests/unit/test_tools_package.py` (append `"transform_geometry"`)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_tool_transform_geometry.py`:

```python
from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.transform_geometry import transform_geometry
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.transform_geometry.get_services", lambda: services)
    return services


def _put_poly(services: Services) -> str:
    return services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-73.6, 45.5], [-73.5, 45.5], [-73.5, 45.6], [-73.6, 45.6], [-73.6, 45.5]]]}, "properties": {"k": 1}}]},
        {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


async def test_transform_geometry_centroid_creates_dataset(services: Services) -> None:
    rid = _put_poly(services)
    r = await transform_geometry.coroutine(dataset_id=rid, op="centroid", alias="centres", tool_call_id="t", state={"datasets": []})
    meta_lite = r.update["datasets"][0]
    assert meta_lite["alias"] == "centres"
    meta = services.store.get_meta(meta_lite["id"])
    assert meta.lineage.parent_ids == [rid]
    assert meta.lineage.operation == "transform_geometry"
    assert meta.lineage.params == {"op": "centroid"}


async def test_transform_geometry_buffer_records_distance_in_lineage(services: Services) -> None:
    rid = _put_poly(services)
    r = await transform_geometry.coroutine(dataset_id=rid, op="buffer", distance_meters=50, alias=None, tool_call_id="t", state={"datasets": []})
    meta = services.store.get_meta(r.update["datasets"][0]["id"])
    assert meta.lineage.params == {"op": "buffer", "distance_meters": 50}


async def test_transform_geometry_buffer_without_distance_is_bad_input(services: Services) -> None:
    rid = _put_poly(services)
    r = await transform_geometry.coroutine(dataset_id=rid, op="buffer", alias=None, tool_call_id="t", state={"datasets": []})
    assert r.update["errors"][0]["code"] == "bad_input"


async def test_transform_geometry_unknown_dataset_returns_error(services: Services) -> None:
    r = await transform_geometry.coroutine(dataset_id="result_999", op="centroid", alias=None, tool_call_id="t", state={"datasets": []})
    assert r.update["errors"][0]["code"] == "dataset_not_found"


async def test_transform_geometry_args_schema_rejects_unknown_op() -> None:
    from pydantic import ValidationError

    schema = transform_geometry.args_schema
    with pytest.raises(ValidationError):
        schema.model_validate({"dataset_id": "result_001", "op": "banana", "tool_call_id": "t", "state": {}})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_tool_transform_geometry.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create the tool**

Create `backend/geo_agent/agent/tools/datasets/transform_geometry.py`:

```python
from typing import Annotated, Literal

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import Field

from geo_agent.agent.error_helpers import (
    dataset_created_command,
    dataset_not_found_command,
    tool_error_command,
)
from geo_agent.agent.registry import get_services
from geo_agent.models import DatasetMetaLite, ToolError
from geo_agent.services.geometry_ops import transform as do_transform


def _meta_lite(meta) -> DatasetMetaLite:
    return DatasetMetaLite(
        id=meta.id,
        alias=meta.alias,
        feature_count=meta.feature_count,
        bbox=meta.bbox,
        layer=meta.source.layer,
        operation=meta.lineage.operation,
    )


@tool
async def transform_geometry(
    dataset_id: str,
    op: Literal["buffer", "centroid", "simplify", "dissolve"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    distance_meters: Annotated[float | None, Field(description="Required for op='buffer'; in metres")] = None,
    tolerance: Annotated[float | None, Field(description="Required for op='simplify'; in degrees, e.g. 0.0001")] = None,
    by: Annotated[str | None, Field(description="For op='dissolve': attribute to merge by; omit to merge everything")] = None,
    alias: Annotated[str | None, Field(description="Short, descriptive name for the new dataset")] = None,
) -> Command:
    """Transform a dataset's geometry, producing a new dataset.

    op:
      "buffer"   — requires distance_meters (metres); grows each geometry by that distance
      "centroid" — replaces each geometry with its centroid (Point)
      "simplify" — requires tolerance (degrees, e.g. 0.0001); Douglas–Peucker simplification
      "dissolve" — merge features; with `by`, one feature per distinct value of that attribute

    Example — 100 m buffer around a set of points:
      {"dataset_id": "result_004", "op": "buffer", "distance_meters": 100, "alias": "rayon_100m"}

    On failure: dataset_not_found (bad dataset_id), bad_input (missing distance_meters/tolerance, or
    a `by` attribute that is not in the dataset).
    """
    services = get_services()
    try:
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, dataset_id, tool_call_id)

    try:
        out = do_transform(gj, op, distance_meters=distance_meters, tolerance=tolerance, by=by)
    except ValueError as e:
        return tool_error_command(
            ToolError(code="bad_input", message=str(e), suggestion="provide the missing parameter and retry"),
            tool_call_id,
        )

    params = {k: v for k, v in {"op": op, "distance_meters": distance_meters, "tolerance": tolerance, "by": by}.items() if v is not None}
    rid = services.store.put(
        out,
        {
            "alias": alias,
            "source": {"type": "derived", "filter_summary": f"{op}({dataset_id})"},
            "lineage": {"parent_ids": [dataset_id], "operation": "transform_geometry", "params": params},
        },
    )
    meta = services.store.get_meta(rid)
    return dataset_created_command(
        _meta_lite(meta),
        tool_result={"dataset_id": rid, "alias": meta.alias, "feature_count": meta.feature_count, "bbox": list(meta.bbox)},
        state=state,
        tool_call_id=tool_call_id,
    )
```

- [ ] **Step 4: Register the tool in `tools/__init__.py`**

Edit `backend/geo_agent/agent/tools/__init__.py`: add `from geo_agent.agent.tools.datasets.transform_geometry import transform_geometry`, add `transform_geometry` to `ALL_TOOLS` (Local dataset tools group), add `"transform_geometry"` to `__all__`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_tool_transform_geometry.py tests/unit/test_tools_package.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd backend
git add geo_agent/agent/tools/datasets/transform_geometry.py geo_agent/agent/tools/__init__.py tests/unit/test_tool_transform_geometry.py tests/unit/test_tools_package.py
git commit -m "feat(tools): add transform_geometry (buffer/centroid/simplify/dissolve)"
```

---

## Task 8: `spatial_join` tool

**Files:**
- Create: `backend/geo_agent/agent/tools/datasets/spatial_join.py`
- Modify: `backend/geo_agent/agent/tools/__init__.py`
- Test: `backend/tests/unit/test_tool_spatial_join.py` (new), `backend/tests/unit/test_tools_package.py` (append `"spatial_join"`)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_tool_spatial_join.py`:

```python
from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.spatial_join import spatial_join
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.spatial_join.get_services", lambda: services)
    return services


def _put(services: Services, geojson: dict, alias: str | None = None) -> str:
    return services.store.put(
        geojson,
        {"alias": alias, "source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


async def test_spatial_join_creates_dataset_with_two_parents(services: Services) -> None:
    pts = _put(services, {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 1]}, "properties": {"id": "p1"}}]}, alias="points")
    zones = _put(services, {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]]]}, "properties": {"zone": "A"}}]}, alias="zones")

    r = await spatial_join.coroutine(left_id=pts, right_id=zones, predicate="within", alias="points_zoned", tool_call_id="t", state={"datasets": []})

    meta_lite = r.update["datasets"][0]
    assert meta_lite["alias"] == "points_zoned"
    meta = services.store.get_meta(meta_lite["id"])
    assert meta.lineage.parent_ids == [pts, zones]
    assert meta.lineage.operation == "spatial_join"
    assert meta.lineage.params == {"predicate": "within"}
    # the joined attribute is present in the stored geojson
    gj = services.store.get_geojson(meta_lite["id"])
    assert gj["features"][0]["properties"]["zone_r"] == "A"


async def test_spatial_join_unknown_right_returns_error(services: Services) -> None:
    pts = _put(services, {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 1]}, "properties": {}}]})
    r = await spatial_join.coroutine(left_id=pts, right_id="result_999", predicate="within", alias=None, tool_call_id="t", state={"datasets": []})
    assert r.update["errors"][0]["code"] == "dataset_not_found"


async def test_spatial_join_args_schema_rejects_unknown_predicate() -> None:
    from pydantic import ValidationError

    schema = spatial_join.args_schema
    with pytest.raises(ValidationError):
        schema.model_validate({"left_id": "result_001", "right_id": "result_002", "predicate": "banana", "tool_call_id": "t", "state": {}})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_tool_spatial_join.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create the tool**

Create `backend/geo_agent/agent/tools/datasets/spatial_join.py`:

```python
from typing import Annotated, Literal

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import Field

from geo_agent.agent.error_helpers import dataset_created_command, dataset_not_found_command
from geo_agent.agent.registry import get_services
from geo_agent.models import DatasetMetaLite
from geo_agent.services.geometry_ops import spatial_join as do_spatial_join


def _meta_lite(meta) -> DatasetMetaLite:
    return DatasetMetaLite(
        id=meta.id,
        alias=meta.alias,
        feature_count=meta.feature_count,
        bbox=meta.bbox,
        layer=meta.source.layer,
        operation=meta.lineage.operation,
    )


@tool
async def spatial_join(
    left_id: str,
    right_id: str,
    predicate: Literal["intersects", "within", "contains"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    alias: Annotated[str | None, Field(description="Short, descriptive name for the new dataset")] = None,
) -> Command:
    """Attach `right`'s attributes to each feature of `left` based on a spatial relation.

    Produces a new dataset with `left`'s geometry. Every `left` feature is kept; when no `right`
    feature satisfies `predicate`, the joined attributes are null. All `right` attribute names get a
    `_r` suffix to avoid collisions. When a `left` feature matches several `right` features, the
    first match wins.

    predicate: "intersects" | "within" | "contains"

    Example — tag each street with the borough it falls in:
      {"left_id": "result_003", "right_id": "result_002", "predicate": "within", "alias": "rues_avec_arrondissement"}

    On failure: dataset_not_found (bad left_id/right_id).
    """
    services = get_services()
    try:
        left_gj = services.store.get_geojson(left_id)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, left_id, tool_call_id)
    try:
        right_gj = services.store.get_geojson(right_id)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, right_id, tool_call_id)

    out = do_spatial_join(left_gj, right_gj, predicate)
    rid = services.store.put(
        out,
        {
            "alias": alias,
            "source": {"type": "derived", "filter_summary": f"sjoin({left_id}, {right_id}, {predicate})"},
            "lineage": {"parent_ids": [left_id, right_id], "operation": "spatial_join", "params": {"predicate": predicate}},
        },
    )
    meta = services.store.get_meta(rid)
    return dataset_created_command(
        _meta_lite(meta),
        tool_result={"dataset_id": rid, "alias": meta.alias, "feature_count": meta.feature_count, "bbox": list(meta.bbox)},
        state=state,
        tool_call_id=tool_call_id,
    )
```

- [ ] **Step 4: Register the tool in `tools/__init__.py`**

Edit `backend/geo_agent/agent/tools/__init__.py`: add `from geo_agent.agent.tools.datasets.spatial_join import spatial_join`, add `spatial_join` to `ALL_TOOLS` (Local dataset tools group), add `"spatial_join"` to `__all__`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_tool_spatial_join.py tests/unit/test_tools_package.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd backend
git add geo_agent/agent/tools/datasets/spatial_join.py geo_agent/agent/tools/__init__.py tests/unit/test_tool_spatial_join.py tests/unit/test_tools_package.py
git commit -m "feat(tools): add spatial_join (left join with _r suffix)"
```

---

## Task 9: `describe_wfs_layer` tool

**Files:**
- Create: `backend/geo_agent/agent/tools/wfs/describe_layer.py`
- Modify: `backend/geo_agent/agent/tools/__init__.py`
- Test: `backend/tests/unit/test_tool_describe_wfs_layer.py` (new), `backend/tests/unit/test_tools_package.py` (append `"describe_wfs_layer"`)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_tool_describe_wfs_layer.py`:

```python
from unittest.mock import AsyncMock

import httpx
import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.wfs.describe_layer import describe_wfs_layer
from geo_agent.config import Settings
from geo_agent.services.wfs_client import FeatureTypeSchema


@pytest.fixture
def services(monkeypatch: pytest.MonkeyPatch) -> Services:
    wfs_mock = AsyncMock()
    wfs_mock.describe_feature_type.return_value = FeatureTypeSchema(
        type_name="montreal:chaussees",
        geom_property="geom",
        attribute_schema={"nom_voie": "string", "longueur": "number"},
    )
    services = Services(settings=Settings(), wfs=wfs_mock, store=None)  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.wfs.describe_layer.get_services", lambda: services)
    return services


async def test_describe_wfs_layer_returns_attributes(services: Services) -> None:
    out = await describe_wfs_layer.coroutine(layer="montreal:chaussees", tool_call_id="t")
    assert out == {
        "layer": "montreal:chaussees",
        "geometry_property": "geom",
        "attributes": {"nom_voie": "string", "longueur": "number"},
    }


async def test_describe_wfs_layer_http_error_returns_layer_not_found(services: Services) -> None:
    services.wfs.describe_feature_type.side_effect = httpx.HTTPStatusError(
        "404", request=httpx.Request("GET", "http://wfs"), response=httpx.Response(404)
    )
    out = await describe_wfs_layer.coroutine(layer="montreal:bogus", tool_call_id="t")
    assert out.update["errors"][0]["code"] == "layer_not_found"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_tool_describe_wfs_layer.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create the tool**

Create `backend/geo_agent/agent/tools/wfs/describe_layer.py`:

```python
from typing import Annotated

import httpx
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from geo_agent.agent.error_helpers import tool_error_command
from geo_agent.agent.registry import get_services
from geo_agent.models import ToolError


@tool
async def describe_wfs_layer(
    layer: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> dict | Command:
    """Return the attribute schema and geometry property of a WFS layer.

    Call this before `select_features` with an `attribute_filter` when you don't know the layer's
    attribute names. No features are returned.

    Output: {"layer", "geometry_property", "attributes": {name: type}} where `type` is one of
    "string" | "number" | "boolean".

    Example:
      {"layer": "montreal:chaussees"}

    On failure: layer_not_found (the WFS server could not describe that layer).
    """
    services = get_services()
    try:
        schema = await services.wfs.describe_feature_type(layer)
    except httpx.HTTPStatusError:
        return tool_error_command(
            ToolError(
                code="layer_not_found",
                message=f"WFS layer {layer!r} not found or not describable",
                suggestion="call list_wfs_layers to see valid layer names",
            ),
            tool_call_id,
        )
    return {"layer": layer, "geometry_property": schema.geom_property, "attributes": schema.attribute_schema}
```

- [ ] **Step 4: Register the tool in `tools/__init__.py`**

Edit `backend/geo_agent/agent/tools/__init__.py`: add `from geo_agent.agent.tools.wfs.describe_layer import describe_wfs_layer`, insert `describe_wfs_layer` into `ALL_TOOLS` right after `list_wfs_layers` (so the WFS group reads `list_wfs_layers, describe_wfs_layer, select_features`), add `"describe_wfs_layer"` to `__all__`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_tool_describe_wfs_layer.py tests/unit/test_tools_package.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd backend
git add geo_agent/agent/tools/wfs/describe_layer.py geo_agent/agent/tools/__init__.py tests/unit/test_tool_describe_wfs_layer.py tests/unit/test_tools_package.py
git commit -m "feat(tools): add describe_wfs_layer"
```

---

## Task 10: `inspect_dataset` tool

**Files:**
- Create: `backend/geo_agent/agent/tools/ui/inspect_dataset.py`
- Modify: `backend/geo_agent/agent/tools/__init__.py`
- Test: `backend/tests/unit/test_tool_inspect_dataset.py` (new), `backend/tests/unit/test_tools_package.py` (append `"inspect_dataset"`)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_tool_inspect_dataset.py`:

```python
import json
from pathlib import Path

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.ui.inspect_dataset import inspect_dataset
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.ui.inspect_dataset.get_services", lambda: services)
    return services


@pytest.fixture
def rid(services: Services) -> str:
    return services.store.put(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-73.6, 45.5]}, "properties": {"nom": "A", "n": 1}},
                {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1], [2, 2]]}, "properties": {"nom": "B", "n": 2}},
            ],
        },
        {"alias": "ds", "source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}},
    )


async def test_inspect_schema_returns_schema_and_sample(services: Services, rid: str) -> None:
    out = await inspect_dataset.coroutine(dataset_id=rid, view="schema", tool_call_id="t")
    assert out["view"] == "schema"
    assert out["dataset_id"] == rid
    assert out["attribute_schema"] == {"nom": "string", "n": "number"}
    assert out["sample"] == {"nom": "A", "n": 1}


async def test_inspect_features_returns_compact_rows_without_coordinates(services: Services, rid: str) -> None:
    out = await inspect_dataset.coroutine(dataset_id=rid, view="features", tool_call_id="t")
    assert out["view"] == "features"
    assert out["total"] == 2
    assert [f["index"] for f in out["features"]] == [0, 1]
    assert out["features"][0]["geometry_type"] == "Point"
    assert out["features"][1]["geometry_type"] == "LineString"
    assert "coordinates" not in json.dumps(out)


async def test_inspect_feature_returns_properties_and_vertex_count(services: Services, rid: str) -> None:
    out = await inspect_dataset.coroutine(dataset_id=rid, view="feature", feature_index=1, tool_call_id="t")
    assert out["view"] == "feature"
    assert out["index"] == 1
    assert out["properties"] == {"nom": "B", "n": 2}
    assert out["geometry_type"] == "LineString"
    assert out["vertex_count"] == 3


async def test_inspect_feature_out_of_range_is_bad_input(services: Services, rid: str) -> None:
    out = await inspect_dataset.coroutine(dataset_id=rid, view="feature", feature_index=99, tool_call_id="t")
    assert out.update["errors"][0]["code"] == "bad_input"


async def test_inspect_unknown_dataset_returns_error(services: Services) -> None:
    out = await inspect_dataset.coroutine(dataset_id="result_999", view="schema", tool_call_id="t")
    assert out.update["errors"][0]["code"] == "dataset_not_found"


async def test_inspect_args_schema_rejects_unknown_view() -> None:
    from pydantic import ValidationError

    schema = inspect_dataset.args_schema
    with pytest.raises(ValidationError):
        schema.model_validate({"dataset_id": "result_001", "view": "banana", "tool_call_id": "t"})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_tool_inspect_dataset.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create the tool**

Create `backend/geo_agent/agent/tools/ui/inspect_dataset.py`:

```python
from typing import Annotated, Any, Literal

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command
from pydantic import Field

from geo_agent.agent.error_helpers import dataset_not_found_command, tool_error_command
from geo_agent.agent.registry import get_services
from geo_agent.models import ToolError

FEATURE_LIST_CAP = 50


def _geometry_type(feature: dict) -> str | None:
    return (feature.get("geometry") or {}).get("type")


def _vertex_count(geom: dict | None) -> int:
    if not geom:
        return 0
    if geom.get("type") == "GeometryCollection":
        return sum(_vertex_count(g) for g in geom.get("geometries", []))

    def walk(c: Any) -> int:
        if isinstance(c, (int, float)):
            return 0
        if isinstance(c, list) and len(c) >= 2 and all(isinstance(x, (int, float)) for x in c[:2]):
            return 1
        if isinstance(c, list):
            return sum(walk(x) for x in c)
        return 0

    return walk(geom.get("coordinates"))


@tool
async def inspect_dataset(
    dataset_id: str,
    view: Literal["schema", "features", "feature"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    feature_index: Annotated[int | None, Field(description="Required for view='feature': 0-based index into the dataset")] = None,
) -> dict | Command:
    """Surface a view of a dataset to the user in the chat (does not change the map).

    view:
      "schema"   — attribute names, types, and a sample value from the first feature
      "features" — a compact table of up to 50 features (properties only; no geometry)
      "feature"  — one feature's full properties + a geometry summary; requires feature_index

    Examples:
      {"dataset_id": "result_003", "view": "schema"}
      {"dataset_id": "result_003", "view": "features"}
      {"dataset_id": "result_003", "view": "feature", "feature_index": 0}

    You receive only property values and a geometry-type summary — never the coordinates.

    On failure: dataset_not_found (bad dataset_id), bad_input (feature_index out of range).
    """
    services = get_services()
    try:
        meta = services.store.get_meta(dataset_id)
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, dataset_id, tool_call_id)

    features = gj.get("features", [])

    if view == "schema":
        sample = (features[0].get("properties") or {}) if features else {}
        return {
            "view": "schema",
            "dataset_id": meta.id,
            "alias": meta.alias,
            "attribute_schema": meta.attribute_schema,
            "sample": sample,
        }

    if view == "features":
        rows = [
            {"index": i, "properties": (f.get("properties") or {}), "geometry_type": _geometry_type(f)}
            for i, f in enumerate(features[:FEATURE_LIST_CAP])
        ]
        return {"view": "features", "dataset_id": meta.id, "alias": meta.alias, "total": len(features), "features": rows}

    # view == "feature"
    if feature_index is None or feature_index < 0 or feature_index >= len(features):
        upper = max(len(features) - 1, 0)
        return tool_error_command(
            ToolError(
                code="bad_input",
                message=f"feature_index out of range (dataset has {len(features)} features)",
                suggestion=f"feature_index must be 0..{upper}",
            ),
            tool_call_id,
        )
    f = features[feature_index]
    return {
        "view": "feature",
        "dataset_id": meta.id,
        "alias": meta.alias,
        "index": feature_index,
        "properties": (f.get("properties") or {}),
        "geometry_type": _geometry_type(f),
        "vertex_count": _vertex_count(f.get("geometry")),
    }
```

- [ ] **Step 4: Register the tool in `tools/__init__.py`**

Edit `backend/geo_agent/agent/tools/__init__.py`: add `from geo_agent.agent.tools.ui.inspect_dataset import inspect_dataset`, add `inspect_dataset` to `ALL_TOOLS` (UI tools group, after `hide_on_map`), add `"inspect_dataset"` to `__all__`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_tool_inspect_dataset.py tests/unit/test_tools_package.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd backend
git add geo_agent/agent/tools/ui/inspect_dataset.py geo_agent/agent/tools/__init__.py tests/unit/test_tool_inspect_dataset.py tests/unit/test_tools_package.py
git commit -m "feat(tools): add inspect_dataset (schema/features/feature views)"
```

---

## Task 11: Rewrite the `# Tool catalog` section of `SYSTEM_PROMPT`

**Files:**
- Modify: `backend/geo_agent/agent/prompts.py`
- Test: `backend/tests/unit/test_prompt_builder.py` (append)

- [ ] **Step 1: Append the failing assertions**

Append to `backend/tests/unit/test_prompt_builder.py`:

```python
def test_system_prompt_has_three_tool_families() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT
    assert "WFS server tools" in SYSTEM_PROMPT
    assert "Local dataset tools" in SYSTEM_PROMPT
    assert "UI tools" in SYSTEM_PROMPT


def test_system_prompt_mentions_new_tools() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT
    for name in ("describe_wfs_layer", "spatial_overlay", "transform_geometry", "spatial_join", "inspect_dataset"):
        assert name in SYSTEM_PROMPT, name


def test_system_prompt_has_empty_result_code() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT
    assert "empty_result" in SYSTEM_PROMPT
```

- [ ] **Step 2: Run the prompt tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_prompt_builder.py -v`
Expected: the three new tests FAIL; the pre-existing ones still pass.

- [ ] **Step 3: Replace `SYSTEM_PROMPT` in `backend/geo_agent/agent/prompts.py`**

Full replacement content for the file `backend/geo_agent/agent/prompts.py`:

```python
SYSTEM_PROMPT = """# Role

You are a geospatial analysis assistant for the City of Montreal open data.
You drive a stack that fetches features from the WFS server (api.accept.montreal.ca)
and runs spatial/statistical queries.

# Core rules

1. **[REQUIRED]** You never see GeoJSON coordinates. Manipulate datasets by their `dataset_id`
   (e.g. `result_001`) and the short `alias` you assign.
2. **[REQUIRED]** Every `select_features` call MUST have a geometry filter. Either:
   - a previous `dataset_id` (typically a user drawing or a prior result), OR
   - a polygon explicitly provided in the user's message.
   Whole-layer downloads are forbidden.
3. **[REQUIRED]** To slice or transform data you already have, prefer the **local dataset tools**
   (`filter_attributes`, `aggregate`, `spatial_overlay`, `transform_geometry`, `spatial_join`) over
   re-querying the WFS.
4. **[RECOMMENDED]** Call `describe_wfs_layer` before a `select_features` with an `attribute_filter`
   if you don't know the layer's attribute names — just as you call `describe_dataset` before
   `filter_attributes`.
5. **[RECOMMENDED]** After producing a meaningful dataset, call `show_on_map` so the user sees it.
6. **[RECOMMENDED]** Always assign a short, descriptive `alias` when creating a dataset.

# User-drawn zones

When the user draws a polygon on the map, it is auto-saved as a dataset with
`operation="user_drawing"` and an alias like `zone_1`, `zone_2`, ...

When the user says "this zone", "cette zone", "the area I drew":
- Look at the "Current datasets in this session" block below.
- Find the most recent dataset with `operation="user_drawing"`.
- Use its `id` (e.g. `result_008`) — NOT its alias — when calling tools.
- Tell the user which zone alias you used: *"I'll search using zone_2 (the polygon you just drew)."*
- If multiple drawings exist and the request is ambiguous, ask the user which one by alias.

# Tool catalog

## WFS server tools (remote — query Montreal's geomatics server)

### list_wfs_layers
Discover which WFS layers are available. Use it the first time you encounter a topic and don't
already know the layer name. Output: `name`, `title`, `abstract` — read the abstract before
picking a layer.

### describe_wfs_layer
Return a WFS layer's attribute names + types and its geometry property. Call this before a
`select_features` with an `attribute_filter` when you don't know the attribute names. No features
are returned.

Example:
  {"layer": "montreal:chaussees"}

### select_features
Fetch features from a WFS layer with a server-side OGC filter. Always returns a new dataset.

Example — search within a user-drawn zone:
  {
    "layer": "montreal:chaussees",
    "geometry_source": {"type": "dataset", "dataset_id": "result_008", "use_geometry": true},
    "spatial_predicate": "within",
    "alias": "chaussees_zone_2"
  }

Example — chain from a previous WFS result using its bbox (fast):
  {
    "layer": "montreal:batiments",
    "geometry_source": {"type": "dataset", "dataset_id": "result_005", "use_geometry": false},
    "spatial_predicate": "intersects",
    "alias": "batiments_pres_parcs"
  }

Example — with a server-side attribute filter (WFS operators only):
  {
    "layer": "montreal:parcs",
    "geometry_source": {"type": "dataset", "dataset_id": "result_002", "use_geometry": true},
    "spatial_predicate": "within",
    "attribute_filter": {"property": "type", "op": "like", "value": "parc%"},
    "alias": "parcs_dans_zone"
  }

WFS operators for `attribute_filter.op`: eq, neq, lt, gt, lte, gte, **like** (% wildcard).
**No `in`** here — see filter_attributes for that.

`use_geometry`:
  - `false` (default) → bbox of the parent dataset (fast, coarser)
  - `true` → union of all geometries (precise; only works if the union is a single Polygon)

## Local dataset tools (in-memory — operate on datasets you already produced)

### filter_attributes
Filter an existing dataset in-memory by an attribute predicate, producing a new dataset.

**Before filtering: if you don't know the attribute names, call `describe_dataset` on the source
dataset to read its `attribute_schema`.**

Example — keep features above a length threshold:
  {"dataset_id": "result_003", "predicate": {"property": "longueur", "op": "gt", "value": 200}, "alias": "longues_chaussees"}

Example — keep features whose type is in a set:
  {"dataset_id": "result_003", "predicate": {"property": "type", "op": "in", "value": ["parc", "place"]}, "alias": "parcs_et_places"}

In-memory operators for `predicate.op`: eq, neq, lt, gt, lte, gte, **in** (membership).
**No `like`** here — use select_features.attribute_filter for server-side wildcard matching.

### aggregate
Compute a statistic over an existing dataset. Use this for any "how many", "what's the average",
"total length" question.

Example — count features grouped by type:
  {"dataset_id": "result_003", "op": "count", "group_by": "type"}

Example — average length:
  {"dataset_id": "result_003", "op": "mean", "attribute": "longueur"}

Ops: count (no attribute needed), sum, mean, min, max (require `attribute`).

### spatial_overlay
Combine two datasets geometrically, producing a new dataset.

`op`:
  - "intersection" / "clip" → keep only the parts of `left` inside `right` (keeps left's attributes;
    non-overlapping features dropped)
  - "union" → geometric union of both layers' features (attributes from both)
  - "difference" → `left` minus the parts overlapping `right` (keeps left's attributes)

Example — streets clipped to a zone:
  {"left_id": "result_003", "right_id": "result_001", "op": "intersection", "alias": "rues_dans_zone"}

### transform_geometry
Transform a dataset's geometry, producing a new dataset.

`op`:
  - "buffer" → requires `distance_meters` (in metres); grows each geometry by that distance
  - "centroid" → replaces each geometry with its centroid (Point)
  - "simplify" → requires `tolerance` (in degrees, e.g. 0.0001)
  - "dissolve" → merge features; with `by` (attribute name), one feature per distinct value

Example — 100 m buffer around a set of points:
  {"dataset_id": "result_004", "op": "buffer", "distance_meters": 100, "alias": "rayon_100m"}

### spatial_join
Attach `right`'s attributes to each feature of `left` based on a spatial relation. Keeps `left`'s
geometry; all `right` attribute names get a `_r` suffix; first match wins; non-matching features get
null joined attributes.

`predicate`: "intersects" | "within" | "contains".

Example — tag each street with the borough it falls in:
  {"left_id": "result_003", "right_id": "result_002", "predicate": "within", "alias": "rues_avec_arrondissement"}

### describe_dataset
Get full metadata for a dataset by id or alias: bbox, attribute_schema, lineage. Geometry is never
returned. Use this to discover attribute names before `filter_attributes` or to refresh your memory.

### list_datasets
Lightweight list of all session datasets (id, alias, layer, count, bbox, operation). The same info
is already injected below — use this tool only if you need to refresh after many operations.

## UI tools (surface a view to the user)

### show_on_map / hide_on_map
Toggle a dataset's visibility on the map. Call `show_on_map` after producing any dataset the user
should see. Call `hide_on_map` when the user asks to remove a layer from view (the data is preserved).

### inspect_dataset
Show the user a view of a dataset in the chat (no map change). `view`:
  - "schema" → attribute names, types, a sample value from the first feature
  - "features" → a compact table of up to 50 features (properties only)
  - "feature" → one feature's full properties + geometry summary; requires `feature_index`

Examples:
  {"dataset_id": "result_003", "view": "schema"}
  {"dataset_id": "result_003", "view": "feature", "feature_index": 0}

# Error handling

When a tool returns an error, read the `code` and `suggestion` fields and adapt:

- `too_many_features` → refine: shrink the area, add an `attribute_filter`, or chain from a smaller
  parent dataset. Never retry the same call.
- `dataset_not_found` → check the "Current datasets" block; the `suggestion` lists available ids.
- `layer_not_found` → call `list_wfs_layers` to get valid layer names.
- `unsupported_geometry` (from `use_geometry=true` returning a MultiPolygon) → retry with
  `use_geometry=false` (bbox) or chain from a single-polygon parent.
- `empty_result` (a `spatial_overlay` / `spatial_join` produced no features) → the inputs probably
  do not overlap; loosen the criterion, change the `op`/`predicate`, or pick different inputs.
  Never retry the same call.
- `bad_input` → fix the malformed or missing argument the suggestion points to and retry once.
- Any other code: read the `message` and `suggestion`, adapt the call accordingly. If the suggestion
  is unclear, ask the user before retrying.

Never apologize about an error to the user before trying to resolve it.
"""
```

- [ ] **Step 4: Run the prompt tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_prompt_builder.py -v`
Expected: PASS (all old + new assertions).

- [ ] **Step 5: Run the whole backend suite**

Run: `cd backend && uv run pytest -q`
Expected: 0 failures.

- [ ] **Step 6: Lint**

Run: `cd backend && uv run ruff check geo_agent tests`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
cd backend
git add geo_agent/agent/prompts.py tests/unit/test_prompt_builder.py
git commit -m "feat(prompt): rewrite tool catalog into 3 families, add new tools + empty_result"
```

---

## Task 12: Frontend — `FeatureWidget.tsx`

**Files:**
- Create: `frontend/components/Widgets/FeatureWidget.tsx`
- Test: `frontend/tests/unit/FeatureWidget.test.tsx` (new)

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/unit/FeatureWidget.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FeatureWidget } from "@/components/Widgets/FeatureWidget";

describe("FeatureWidget", () => {
  it("renders the property table and geometry summary", () => {
    render(
      <FeatureWidget
        data={{
          view: "feature",
          dataset_id: "result_003",
          alias: "rues",
          index: 2,
          properties: { nom_voie: "Rue X", longueur: 120 },
          geometry_type: "LineString",
          vertex_count: 4,
        }}
      />
    );
    expect(screen.getByText("rues")).toBeInTheDocument();
    expect(screen.getByText(/#2/)).toBeInTheDocument();
    expect(screen.getByText("nom_voie")).toBeInTheDocument();
    expect(screen.getByText('"Rue X"')).toBeInTheDocument();
    expect(screen.getByText("longueur")).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(screen.getByText("LineString")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- FeatureWidget`
Expected: FAIL — module not found.

- [ ] **Step 3: Create the component**

Create `frontend/components/Widgets/FeatureWidget.tsx`:

```tsx
"use client";

import React from "react";

export interface FeatureWidgetData {
  view: "feature";
  dataset_id: string;
  alias: string | null;
  index: number;
  properties: Record<string, unknown>;
  geometry_type: string | null;
  vertex_count: number;
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return `"${v}"`;
  return String(v);
}

export function FeatureWidget({ data }: { data: FeatureWidgetData }) {
  const props = data.properties ?? {};
  return (
    <div style={card}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={badge}>FEATURE</span>
        <strong style={{ fontSize: 15 }}>{data.alias ?? data.dataset_id}</strong>
        <span style={{ color: "#64748b", fontSize: 12 }}>· #{data.index}</span>
      </div>

      <div style={sectionLabel}>Propriétés</div>
      <table style={tbl}>
        <tbody>
          {Object.entries(props).map(([k, v]) => (
            <tr key={k} style={{ borderBottom: "1px solid #f1f5f9" }}>
              <td style={{ padding: "5px 8px", color: "#64748b", fontFamily: "monospace" }}>{k}</td>
              <td style={{ padding: "5px 8px", textAlign: "right" }}>{fmt(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={sectionLabel}>Géométrie</div>
      <table style={tbl}>
        <tbody>
          <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
            <td style={{ padding: "5px 8px", color: "#64748b" }}>Type</td>
            <td style={{ padding: "5px 8px", textAlign: "right" }}>{data.geometry_type ?? "—"}</td>
          </tr>
          <tr>
            <td style={{ padding: "5px 8px", color: "#64748b" }}>Vertices</td>
            <td style={{ padding: "5px 8px", textAlign: "right", fontFamily: "monospace" }}>{data.vertex_count}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

const card: React.CSSProperties = { background: "#f8fafc", padding: 16, borderRadius: 8, fontFamily: "system-ui", fontSize: 13, color: "#0f172a" };
const badge: React.CSSProperties = { background: "#fbbf24", color: "#78350f", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 };
const sectionLabel: React.CSSProperties = { fontSize: 9, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5, margin: "10px 0 4px" };
const tbl: React.CSSProperties = { width: "100%", borderCollapse: "collapse", fontSize: 12, background: "white", border: "1px solid #e2e8f0", borderRadius: 6 };
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- FeatureWidget`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd frontend
git add components/Widgets/FeatureWidget.tsx tests/unit/FeatureWidget.test.tsx
git commit -m "feat(widgets): add FeatureWidget"
```

---

## Task 13: Frontend — `FeatureListWidget.tsx`

**Files:**
- Create: `frontend/components/Widgets/FeatureListWidget.tsx`
- Test: `frontend/tests/unit/FeatureListWidget.test.tsx` (new)

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/unit/FeatureListWidget.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FeatureListWidget } from "@/components/Widgets/FeatureListWidget";

const DATA = {
  view: "features" as const,
  dataset_id: "result_003",
  alias: "rues",
  total: 120,
  features: [
    { index: 0, properties: { nom_voie: "Rue A", longueur: 100, surface: "asphalte", arrond: "Plateau" }, geometry_type: "LineString" },
    { index: 1, properties: { nom_voie: "Rue B", longueur: 250, surface: "béton", arrond: "Sud-Ouest" }, geometry_type: "LineString" },
  ],
};

describe("FeatureListWidget", () => {
  it("renders one row per feature and shows total / displayed count", () => {
    render(<FeatureListWidget data={DATA} />);
    expect(screen.getByText("Rue A")).toBeInTheDocument();
    expect(screen.getByText("Rue B")).toBeInTheDocument();
    expect(screen.getByText(/120 features/)).toBeInTheDocument();
    expect(screen.getByText(/affichées/)).toBeInTheDocument();
  });

  it("expands a row to reveal properties not shown as columns", () => {
    render(<FeatureListWidget data={DATA} />);
    expect(screen.queryByText("Plateau")).toBeNull();
    fireEvent.click(screen.getByText("Rue A"));
    expect(screen.getByText("Plateau")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- FeatureListWidget`
Expected: FAIL — module not found.

- [ ] **Step 3: Create the component**

Create `frontend/components/Widgets/FeatureListWidget.tsx`:

```tsx
"use client";

import React, { useState } from "react";

export interface FeatureRow {
  index: number;
  properties: Record<string, unknown>;
  geometry_type: string | null;
}

export interface FeatureListWidgetData {
  view: "features";
  dataset_id: string;
  alias: string | null;
  total: number;
  features: FeatureRow[];
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  return String(v);
}

export function FeatureListWidget({ data }: { data: FeatureListWidgetData }) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const rows = data.features ?? [];

  const cols: string[] = [];
  for (const r of rows) {
    for (const k of Object.keys(r.properties ?? {})) {
      if (!cols.includes(k)) cols.push(k);
      if (cols.length >= 3) break;
    }
    if (cols.length >= 3) break;
  }

  const toggle = (i: number) =>
    setOpen((prev) => {
      const n = new Set(prev);
      if (n.has(i)) n.delete(i);
      else n.add(i);
      return n;
    });

  return (
    <div style={card}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={badge}>FEATURES</span>
        <strong style={{ fontSize: 15 }}>{data.alias ?? data.dataset_id}</strong>
        <span style={{ color: "#64748b", fontSize: 12 }}>
          · {data.total} features{data.total > rows.length ? ` (affichées : ${rows.length})` : ""}
        </span>
      </div>

      <div style={{ background: "white", borderRadius: 6, border: "1px solid #e2e8f0", overflow: "auto", maxHeight: 320 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ background: "#f1f5f9", textAlign: "left" }}>
              <th style={th}>#</th>
              {cols.map((c) => (
                <th key={c} style={th}>{c}</th>
              ))}
              <th style={th}>géom.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const isOpen = open.has(r.index);
              return (
                <React.Fragment key={r.index}>
                  <tr style={{ borderTop: "1px solid #f1f5f9", cursor: "pointer" }} onClick={() => toggle(r.index)}>
                    <td style={td}>{r.index}</td>
                    {cols.map((c) => (
                      <td key={c} style={td}>{fmt((r.properties ?? {})[c])}</td>
                    ))}
                    <td style={td}>{r.geometry_type ?? "—"}</td>
                  </tr>
                  {isOpen && (
                    <tr key={`${r.index}-detail`}>
                      <td colSpan={cols.length + 2} style={{ padding: "6px 10px", background: "#f8fafc" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                          <tbody>
                            {Object.entries(r.properties ?? {}).map(([k, v]) => (
                              <tr key={k}>
                                <td style={{ padding: "3px 6px", color: "#64748b", fontFamily: "monospace" }}>{k}</td>
                                <td style={{ padding: "3px 6px", textAlign: "right" }}>{fmt(v)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const card: React.CSSProperties = { background: "#f8fafc", padding: 16, borderRadius: 8, fontFamily: "system-ui", fontSize: 13, color: "#0f172a" };
const badge: React.CSSProperties = { background: "#0ea5e9", color: "white", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 };
const th: React.CSSProperties = { padding: "6px 10px", fontWeight: 600, color: "#475569", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 };
const td: React.CSSProperties = { padding: "6px 10px" };
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- FeatureListWidget`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd frontend
git add components/Widgets/FeatureListWidget.tsx tests/unit/FeatureListWidget.test.tsx
git commit -m "feat(widgets): add FeatureListWidget"
```

---

## Task 14: Frontend — `InspectDatasetWidget`, `SchemaWidget` sample prop, `lib/types.ts`

**Files:**
- Create: `frontend/components/Widgets/InspectDatasetWidget.tsx`
- Modify: `frontend/components/Widgets/SchemaWidget.tsx`, `frontend/lib/types.ts`
- Test: `frontend/tests/unit/InspectDatasetWidget.test.tsx` (new)

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/unit/InspectDatasetWidget.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InspectDatasetWidget } from "@/components/Widgets/InspectDatasetWidget";

describe("InspectDatasetWidget", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ features: [] }), { status: 200 })));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("renders SchemaWidget for view=schema using the inline sample (no fetch)", () => {
    render(
      <InspectDatasetWidget
        data={{
          view: "schema",
          dataset_id: "result_002",
          alias: "routes",
          attribute_schema: { nom_voie: "string", longueur: "number" },
          sample: { nom_voie: "Rue X", longueur: 42 },
        }}
      />
    );
    expect(screen.getByText("nom_voie")).toBeInTheDocument();
    expect(screen.getByText('"Rue X"')).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("renders FeatureWidget for view=feature", () => {
    render(
      <InspectDatasetWidget
        data={{ view: "feature", dataset_id: "result_003", alias: null, index: 0, properties: { k: 1 }, geometry_type: "Point", vertex_count: 1 }}
      />
    );
    expect(screen.getByText("FEATURE")).toBeInTheDocument();
    expect(screen.getByText("Point")).toBeInTheDocument();
  });

  it("renders FeatureListWidget for view=features", () => {
    render(
      <InspectDatasetWidget
        data={{ view: "features", dataset_id: "result_003", alias: null, total: 1, features: [{ index: 0, properties: { k: "v" }, geometry_type: "Point" }] }}
      />
    );
    expect(screen.getByText("FEATURES")).toBeInTheDocument();
    expect(screen.getByText("v")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- InspectDatasetWidget`
Expected: FAIL — module not found.

- [ ] **Step 3: Add the optional `sample` prop to `SchemaWidget`**

Edit `frontend/components/Widgets/SchemaWidget.tsx` — change the `Props` interface and the component signature/effect:

```tsx
interface Props {
  data: {
    id: string;
    alias: string | null;
    attribute_schema: Record<string, string>;
  };
  datasetId: string;
  sample?: Record<string, unknown>;
}

export function SchemaWidget({ data, datasetId, sample }: Props) {
  const [example, setExample] = useState<Record<string, unknown> | null>(sample ?? null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (sample) return; // already supplied — no need to fetch the first feature
    fetch(`/api/datasets/${encodeURIComponent(datasetId)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("fetch failed"))))
      .then((gj) => setExample(gj.features?.[0]?.properties ?? {}))
      .catch(() => setExample({}));
  }, [datasetId, sample]);

  // ...rest of the component unchanged
```

Everything below the `useEffect` stays exactly as it is.

- [ ] **Step 4: Add the `inspect_dataset` payload schemas to `lib/types.ts`**

Append to `frontend/lib/types.ts`:

```ts
export const InspectSchemaResult = z.object({
  view: z.literal("schema"),
  dataset_id: z.string(),
  alias: z.string().nullable(),
  attribute_schema: z.record(z.string(), z.string()),
  sample: z.record(z.string(), z.unknown()),
});

export const InspectFeatureRow = z.object({
  index: z.number(),
  properties: z.record(z.string(), z.unknown()),
  geometry_type: z.string().nullable(),
});

export const InspectFeaturesResult = z.object({
  view: z.literal("features"),
  dataset_id: z.string(),
  alias: z.string().nullable(),
  total: z.number(),
  features: z.array(InspectFeatureRow),
});

export const InspectFeatureResult = z.object({
  view: z.literal("feature"),
  dataset_id: z.string(),
  alias: z.string().nullable(),
  index: z.number(),
  properties: z.record(z.string(), z.unknown()),
  geometry_type: z.string().nullable(),
  vertex_count: z.number(),
});

export const InspectResult = z.discriminatedUnion("view", [InspectSchemaResult, InspectFeaturesResult, InspectFeatureResult]);
export type InspectResult = z.infer<typeof InspectResult>;
```

- [ ] **Step 5: Create `InspectDatasetWidget.tsx`**

Create `frontend/components/Widgets/InspectDatasetWidget.tsx`:

```tsx
"use client";

import type { InspectResult } from "@/lib/types";
import { FeatureListWidget } from "./FeatureListWidget";
import { FeatureWidget } from "./FeatureWidget";
import { SchemaWidget } from "./SchemaWidget";

export function InspectDatasetWidget({ data }: { data: InspectResult }) {
  if (data.view === "schema") {
    return (
      <SchemaWidget
        data={{ id: data.dataset_id, alias: data.alias, attribute_schema: data.attribute_schema }}
        datasetId={data.dataset_id}
        sample={data.sample}
      />
    );
  }
  if (data.view === "feature") {
    return <FeatureWidget data={data} />;
  }
  return <FeatureListWidget data={data} />;
}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd frontend && npm test -- InspectDatasetWidget`
Expected: PASS.

- [ ] **Step 7: Run the whole frontend test suite (no regressions to `SchemaWidget`)**

Run: `cd frontend && npm test`
Expected: all tests pass (the existing `SchemaWidget.test.tsx` still passes since it does not pass `sample`).

- [ ] **Step 8: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
cd frontend
git add components/Widgets/InspectDatasetWidget.tsx components/Widgets/SchemaWidget.tsx lib/types.ts tests/unit/InspectDatasetWidget.test.tsx
git commit -m "feat(widgets): add InspectDatasetWidget dispatcher; SchemaWidget accepts inline sample"
```

---

## Task 15: Wire `inspect_dataset` into `GeoPage`

**Files:**
- Modify: `frontend/components/GeoPage.tsx`

- [ ] **Step 1: Add the import**

In `frontend/components/GeoPage.tsx`, add to the import block:

```tsx
import { InspectDatasetWidget } from "@/components/Widgets/InspectDatasetWidget";
```

- [ ] **Step 2: Register the `inspect_dataset` renderer**

In `GeoPageBody`, after the existing `useCopilotAction({ name: "filter_attributes", ... })` block, add:

```tsx
  useCopilotAction({
    name: "inspect_dataset",
    available: "disabled",
    render: ({ result, status }) => {
      if (status === "executing" || !result) {
        return <div style={{ opacity: 0.6, fontSize: 12, padding: 8 }}>Chargement de la vue…</div>;
      }
      return <InspectDatasetWidget data={result as never} />;
    },
  });
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 4: Run the frontend test suite**

Run: `cd frontend && npm test`
Expected: all tests pass (no test targets `GeoPage` directly; this confirms nothing else broke).

- [ ] **Step 5: Commit**

```bash
cd frontend
git add components/GeoPage.tsx
git commit -m "feat(frontend): render inspect_dataset results via InspectDatasetWidget"
```

---

## Task 16: Final verification

- [ ] **Step 1: Backend — full suite**

Run: `cd backend && uv run pytest -q`
Expected: 0 failures.

- [ ] **Step 2: Backend — lint**

Run: `cd backend && uv run ruff check geo_agent tests`
Expected: clean. (Run `uv run ruff check --fix geo_agent tests` if it flags auto-fixable issues, then re-run, then `git add -A && git commit -m "chore(lint): ruff auto-fixes"` if anything changed.)

- [ ] **Step 3: Frontend — tests + typecheck**

Run: `cd frontend && npm test && npm run typecheck`
Expected: tests pass, no type errors.

- [ ] **Step 4: Smoke the agent against Ollama (optional manual step)**

If Ollama + the configured model are running locally:

```bash
cd backend && uv run python -c "
import asyncio
from geo_agent.agent.graph import build_agent
from geo_agent.agent.registry import init_services
from geo_agent.agent.state import build_initial_state
from geo_agent.config import Settings

async def main():
    s = Settings()
    init_services(s)
    agent = build_agent(s)
    state = build_initial_state()
    state['messages'] = [{'role': 'user', 'content': 'List the available WFS layers about parks, then describe one of them.'}]
    out = await agent.ainvoke(state, config={'configurable': {'thread_id': 'smoke'}})
    print(out['messages'][-1].content)

asyncio.run(main())
"
```

Expected: the agent calls `list_wfs_layers` then `describe_wfs_layer` and reports an attribute list.

- [ ] **Step 5: Done — no extra commit needed if everything was committed task-by-task.**

---

## Self-review checklist

- [x] **Spec coverage:** Three subpackages (Task 1). `describe_wfs_layer` (Task 9). `spatial_overlay` (Tasks 2, 6). `transform_geometry` (Tasks 3, 7). `spatial_join` (Tasks 4, 8). `inspect_dataset` backend (Task 10) + frontend widgets (Tasks 12–15). `geometry_ops.py` new module (Tasks 2–4). EPSG:32188 reproject for buffer (Task 3). `empty_result` code in tools (Tasks 6, 8) and prompt (Task 11). Prompt rewrite into 3 families (Task 11). `SchemaWidget` reuse with inline `sample` (Task 14). No `AgentState` / REST changes (none in the plan). `dataset_not_found_command` helper (Task 5) — supports the new tools.
- [x] **No placeholders:** every code step shows complete code; every test step shows the full test.
- [x] **Type consistency:** `_meta_lite` defined identically in each producing tool; `DatasetMetaLite` fields match `models.py`; `OverlayOp`/`TransformOp`/`JoinPredicate` literals match between `geometry_ops.py` and the tools; `inspect_dataset` `view` literals match between the tool, `InspectDatasetWidget`, and `lib/types.ts`; `ALL_TOOLS` grows by exactly one entry per tool task; `test_tools_package.py` `expected` set grows in lockstep.
- [x] **TDD ordering:** every implementation task writes the failing test first, runs it red, implements, runs it green, commits.
- [x] **Frequent commits:** one commit per task (plus an optional lint commit in Task 16).
