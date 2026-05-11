# Tooling & Prompt Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten the geo-agent's tool schemas and rewrite the system prompt so tool-calling becomes more reliable, especially on smaller/local models.

**Architecture:** Replace `dict`-typed tool parameters with Pydantic discriminated unions and models so `@tool` emits structured JSON schemas to the LLM. Align `list_wfs_layers` output with its docstring. Rewrite `SYSTEM_PROMPT` from scratch into a sectioned document (role, rules, tool catalog with examples, error strategy).

**Tech Stack:** Python 3.12, pydantic v2, langchain_core.tools, langgraph, pytest.

**Decisions locked in:**
- Operators stay distinct between `select_features.attribute_filter` (WFS: `eq, neq, lt, gt, lte, gte, like`) and `filter_attributes.predicate` (in-memory: `eq, neq, lt, gt, lte, gte, in`). We document the asymmetry sharply rather than harmonizing implementations.
- System prompt is rewritten end-to-end into sectioned form.
- No live/E2E test — unit tests only.

---

## File Structure

**Modified files:**
- `backend/geo_agent/agent/tools/list_wfs_layers.py` — add `abstract` to output
- `backend/geo_agent/agent/tools/select_features.py` — type `geometry_source` and `attribute_filter` with Pydantic
- `backend/geo_agent/agent/tools/filter_attributes.py` — type `predicate` with Pydantic
- `backend/geo_agent/agent/prompts.py` — full rewrite of `SYSTEM_PROMPT`
- `backend/tests/unit/test_tool_list_wfs_layers.py` — assert `abstract` present
- `backend/tests/unit/test_tool_select_features.py` — assert schema validation rejects bad inputs
- `backend/tests/unit/test_tool_filter_attributes.py` — assert schema validation rejects bad inputs

No new files. The Pydantic input models stay co-located with their tool to keep tool definitions self-contained.

---

## Task 1: Add `abstract` to `list_wfs_layers` output

**Files:**
- Modify: `backend/geo_agent/agent/tools/list_wfs_layers.py`
- Test: `backend/tests/unit/test_tool_list_wfs_layers.py`

- [ ] **Step 1: Read the current test to follow its pattern**

```bash
cat backend/tests/unit/test_tool_list_wfs_layers.py
```

- [ ] **Step 2: Add a failing test asserting `abstract` is returned**

Edit `backend/tests/unit/test_tool_list_wfs_layers.py` and add (or update an existing test) so the WFS mock returns a layer with an `abstract` field and the test asserts it appears in the tool output:

```python
async def test_list_wfs_layers_includes_abstract(monkeypatch: pytest.MonkeyPatch) -> None:
    from geo_agent.agent.registry import Services
    from geo_agent.agent.tools import list_wfs_layers as mod
    from geo_agent.config import Settings
    from geo_agent.models import WFSLayer
    from unittest.mock import AsyncMock

    wfs_mock = AsyncMock()
    wfs_mock.get_layers.return_value = [
        WFSLayer(
            name="montreal:parcs",
            title="Parcs",
            abstract="Parcs et espaces verts de la Ville",
            default_crs="EPSG:4326",
        ),
    ]
    services = Services(settings=Settings(), wfs=wfs_mock, store=None)  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.list_wfs_layers.get_services", lambda: services)

    out = await mod.list_wfs_layers.coroutine()

    assert out == [{"name": "montreal:parcs", "title": "Parcs", "abstract": "Parcs et espaces verts de la Ville"}]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_tool_list_wfs_layers.py::test_list_wfs_layers_includes_abstract -v`
Expected: FAIL — assertion mismatch (current output lacks `abstract`).

- [ ] **Step 4: Update the tool to include `abstract`**

Edit `backend/geo_agent/agent/tools/list_wfs_layers.py`:

```python
from langchain_core.tools import tool

from geo_agent.agent.registry import get_services


@tool
async def list_wfs_layers() -> list[dict]:
    """List all WFS layers available on the Montreal geomatics server.

    Returns one entry per layer with:
      - name: technical id you pass to select_features (e.g. "montreal:parcs")
      - title: short human-readable label
      - abstract: longer description; use it to pick the right layer

    Call this whenever the user asks about a topic and you don't already know
    which layer holds the data.
    """
    services = get_services()
    layers = await services.wfs.get_layers()
    return [
        {"name": l.name, "title": l.title, "abstract": l.abstract or ""}
        for l in layers
    ]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/test_tool_list_wfs_layers.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/geo_agent/agent/tools/list_wfs_layers.py backend/tests/unit/test_tool_list_wfs_layers.py
git commit -m "feat(tools): include abstract in list_wfs_layers output"
```

---

## Task 2: Type `select_features.geometry_source` as a Pydantic discriminated union

**Files:**
- Modify: `backend/geo_agent/agent/tools/select_features.py`
- Test: `backend/tests/unit/test_tool_select_features.py`

**Why this matters:** Currently `geometry_source: dict` means the LLM sees no JSON schema for this parameter. A discriminated union surfaces the two shapes (`type: "polygon"` vs `type: "dataset"`) in the auto-generated tool schema.

- [ ] **Step 1: Add a failing test that exercises Pydantic validation via the tool args_schema**

Append to `backend/tests/unit/test_tool_select_features.py`:

```python
async def test_select_features_args_schema_rejects_unknown_geometry_source_type(services: Services) -> None:
    from pydantic import ValidationError

    schema = select_features.args_schema
    with pytest.raises(ValidationError):
        schema.model_validate({
            "layer": "montreal:parcs",
            "geometry_source": {"type": "banana", "polygon": {}},
            "spatial_predicate": "within",
        })


async def test_select_features_args_schema_accepts_dataset_source(services: Services) -> None:
    schema = select_features.args_schema
    validated = schema.model_validate({
        "layer": "montreal:parcs",
        "geometry_source": {"type": "dataset", "dataset_id": "result_001", "use_geometry": False},
        "spatial_predicate": "within",
    })
    assert validated.geometry_source.type == "dataset"
    assert validated.geometry_source.dataset_id == "result_001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_tool_select_features.py -v -k args_schema`
Expected: FAIL — current `dict` annotation doesn't enforce the discriminator.

- [ ] **Step 3: Update `select_features.py` to use the discriminated union**

Edit `backend/geo_agent/agent/tools/select_features.py`. Replace the existing parameter annotation and the manual `model_validate` block. Key changes:

```python
from typing import Annotated, Any, Literal, Union

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, Field
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from geo_agent.agent.error_helpers import dataset_created_command, tool_error_command
from geo_agent.agent.registry import get_services
from geo_agent.models import DatasetMetaLite, ToolError
from geo_agent.services.ogc_filter import AttributeFilter, SpatialFilter
from geo_agent.services.wfs_client import TooManyFeaturesError


class PolygonSource(BaseModel):
    """A user-provided GeoJSON Polygon (typically from a map drawing tool)."""

    type: Literal["polygon"]
    polygon: dict = Field(description="GeoJSON Polygon geometry")


class DatasetSource(BaseModel):
    """Chain from an existing dataset's geometry."""

    type: Literal["dataset"]
    dataset_id: str = Field(description="Existing dataset id, e.g. result_001 or a user_drawing id")
    use_geometry: bool = Field(
        default=False,
        description=(
            "False (default): use the dataset's bbox as the filter polygon — fast, coarser. "
            "True: union the dataset's geometries — precise, only works if the union is a single Polygon."
        ),
    )


GeometrySource = Annotated[
    Union[PolygonSource, DatasetSource],
    Field(discriminator="type"),
]


class AttributeFilterInput(BaseModel):
    """Server-side attribute filter for the WFS query. Uses OGC operators."""

    property: str = Field(description="Attribute name from the layer's schema")
    op: Literal["eq", "neq", "lt", "gt", "lte", "gte", "like"] = Field(
        description=(
            "OGC server-side operator. Note: 'in' is NOT supported here — use filter_attributes "
            "for in-memory 'in' filtering. 'like' uses % as wildcard."
        ),
    )
    value: Any = Field(description="Comparison value (string/number)")


def _bbox_polygon(bbox: tuple[float, float, float, float]) -> dict:
    minx, miny, maxx, maxy = bbox
    return {
        "type": "Polygon",
        "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]],
    }


def _union_dataset_geometries(geojson: dict) -> dict:
    geoms = [shape(f["geometry"]) for f in geojson.get("features", []) if f.get("geometry")]
    if not geoms:
        raise ValueError("dataset has no geometries")
    merged = unary_union(geoms)
    return mapping(merged)


@tool
async def select_features(
    layer: str,
    geometry_source: GeometrySource,
    spatial_predicate: Literal["intersects", "within", "contains", "bbox", "dwithin"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    alias: Annotated[str | None, Field(description="Short human-readable name for the new dataset")] = None,
    attribute_filter: AttributeFilterInput | None = None,
    distance_meters: float | None = None,
) -> Command:
    """Select features from a WFS layer with a server-side OGC filter.

    Always returns a fresh dataset; never modifies the input.

    geometry_source examples:
      {"type": "polygon", "polygon": {...GeoJSON Polygon...}}                    # user drawing
      {"type": "dataset", "dataset_id": "result_003", "use_geometry": false}     # bbox of result_003
      {"type": "dataset", "dataset_id": "zone_1_id",   "use_geometry": true}     # geometry of zone_1

    spatial_predicate:
      intersects | within | contains | bbox | dwithin (requires distance_meters)

    attribute_filter (optional, server-side):
      {"property": "type", "op": "eq", "value": "parc"}
      Operators: eq, neq, lt, gt, lte, gte, like (NO 'in' — use filter_attributes for that).

    Returns: {"dataset_id", "alias", "feature_count", "bbox", "attribute_schema"}.
    On failure, an error is stored in state.errors and surfaced as a ToolMessage with code:
      too_many_features, dataset_not_found, unsupported_geometry, bad_input.
    """
    services = get_services()
    gsrc = geometry_source  # already validated by args_schema

    if isinstance(gsrc, PolygonSource):
        geom = gsrc.polygon
        parent_ids: list[str] = []
        filter_summary = f"{spatial_predicate}(user_polygon)"
    else:
        try:
            meta = services.store.get_meta(gsrc.dataset_id)
        except FileNotFoundError:
            known = [m.id for m in services.store.list()]
            return tool_error_command(
                ToolError(
                    code="dataset_not_found",
                    message=f"No dataset {gsrc.dataset_id}",
                    suggestion=f"Available IDs: {', '.join(known) if known else '(none)'}",
                ),
                tool_call_id,
            )
        parent_ids = [gsrc.dataset_id]
        if gsrc.use_geometry:
            gj = services.store.get_geojson(gsrc.dataset_id)
            geom = _union_dataset_geometries(gj)
            if geom["type"] != "Polygon":
                return tool_error_command(
                    ToolError(
                        code="unsupported_geometry",
                        message=(
                            f"Unioned geometry of {gsrc.dataset_id} is {geom['type']}; "
                            "only Polygon is supported as a spatial filter today."
                        ),
                        suggestion=(
                            "Use use_geometry=false (bbox) or chain from a dataset whose "
                            "features form a single polygon."
                        ),
                    ),
                    tool_call_id,
                )
            filter_summary = f"{spatial_predicate}(geometry of {gsrc.dataset_id})"
        else:
            geom = _bbox_polygon(meta.bbox)
            filter_summary = f"{spatial_predicate}(bbox of {gsrc.dataset_id})"

    schema = await services.wfs.describe_feature_type(layer)
    geom_property = schema.geom_property

    if spatial_predicate == "dwithin":
        if distance_meters is None:
            return tool_error_command(
                ToolError(code="bad_input", message="dwithin requires distance_meters"),
                tool_call_id,
            )
        sf = SpatialFilter(predicate="dwithin", geometry=geom, geom_property=geom_property, distance_meters=distance_meters)
    else:
        sf = SpatialFilter(predicate=spatial_predicate, geometry=geom, geom_property=geom_property)

    af: AttributeFilter | None = None
    if attribute_filter is not None:
        af = AttributeFilter(property=attribute_filter.property, op=attribute_filter.op, value=attribute_filter.value)

    try:
        gj = await services.wfs.get_features(
            layer=layer,
            spatial_filter=sf,
            attribute_filter=af,
            max_features=services.settings.MAX_FEATURES_PER_QUERY,
        )
    except TooManyFeaturesError as e:
        return tool_error_command(
            ToolError(
                code="too_many_features",
                message=str(e),
                suggestion="Refine the area, add an attribute_filter, or chain from a smaller dataset.",
            ),
            tool_call_id,
        )

    rid = services.store.put(
        gj,
        {
            "alias": alias,
            "source": {"type": "wfs", "layer": layer, "filter_summary": filter_summary},
            "lineage": {
                "parent_ids": parent_ids,
                "operation": "select_features",
                "params": {"layer": layer, "spatial_predicate": spatial_predicate},
            },
        },
    )
    meta = services.store.get_meta(rid)
    meta_lite = DatasetMetaLite(
        id=meta.id,
        alias=meta.alias,
        feature_count=meta.feature_count,
        bbox=meta.bbox,
        layer=meta.source.layer,
        operation=meta.lineage.operation,
    )
    return dataset_created_command(
        meta_lite,
        tool_result={
            "dataset_id": rid,
            "alias": meta.alias,
            "feature_count": meta.feature_count,
            "bbox": list(meta.bbox),
            "attribute_schema": meta.attribute_schema,
        },
        state=state,
        tool_call_id=tool_call_id,
    )
```

- [ ] **Step 4: Update existing tests that pass dicts to also test through args_schema**

The existing tests call `select_features.coroutine(geometry_source={"type": "polygon", ...})` — these bypass Pydantic validation. The function body now expects Pydantic instances. Update each call site in `backend/tests/unit/test_tool_select_features.py`:

For each existing test, wrap dict inputs with the Pydantic model before invoking. Example transformation:

```python
# before
result = await select_features.coroutine(
    layer="montreal:parcs",
    geometry_source={"type": "polygon", "polygon": polygon},
    ...
)

# after
from geo_agent.agent.tools.select_features import PolygonSource, DatasetSource

result = await select_features.coroutine(
    layer="montreal:parcs",
    geometry_source=PolygonSource(type="polygon", polygon=polygon),
    ...
)
```

Apply this pattern to all 5 existing tests in the file (polygon, chain bbox, too-many, unknown dataset, use_geometry=true, multipolygon).

Also update `test_select_features_too_many_returns_command_with_error`: drop the manual `bad_input` check for invalid geometry_source if any — those are now caught upstream by args_schema validation, not the function body.

- [ ] **Step 5: Run the whole select_features test file**

Run: `cd backend && uv run pytest tests/unit/test_tool_select_features.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/geo_agent/agent/tools/select_features.py backend/tests/unit/test_tool_select_features.py
git commit -m "refactor(tools): type select_features inputs with Pydantic discriminated union"
```

---

## Task 3: Type `filter_attributes.predicate` with Pydantic

**Files:**
- Modify: `backend/geo_agent/agent/tools/filter_attributes.py`
- Test: `backend/tests/unit/test_tool_filter_attributes.py`

- [ ] **Step 1: Add a failing test that exercises Pydantic validation via args_schema**

Append to `backend/tests/unit/test_tool_filter_attributes.py`:

```python
async def test_filter_attributes_args_schema_rejects_unknown_op() -> None:
    from pydantic import ValidationError
    from geo_agent.agent.tools.filter_attributes import filter_attributes

    schema = filter_attributes.args_schema
    with pytest.raises(ValidationError):
        schema.model_validate({
            "dataset_id": "result_001",
            "predicate": {"property": "type", "op": "like", "value": "parc%"},  # 'like' not allowed here
        })


async def test_filter_attributes_args_schema_accepts_in_operator() -> None:
    from geo_agent.agent.tools.filter_attributes import filter_attributes

    schema = filter_attributes.args_schema
    validated = schema.model_validate({
        "dataset_id": "result_001",
        "predicate": {"property": "type", "op": "in", "value": ["parc", "place"]},
    })
    assert validated.predicate.op == "in"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_tool_filter_attributes.py -v -k args_schema`
Expected: FAIL (current `predicate: dict` doesn't constrain `op`).

- [ ] **Step 3: Update `filter_attributes.py` to use the Pydantic model directly**

Edit `backend/geo_agent/agent/tools/filter_attributes.py`:

```python
from typing import Annotated

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from geo_agent.agent.error_helpers import dataset_created_command, tool_error_command
from geo_agent.agent.registry import get_services
from geo_agent.models import DatasetMetaLite, ToolError
from geo_agent.services.spatial_ops import AttributePredicate, filter_by_attribute


@tool
async def filter_attributes(
    dataset_id: str,
    predicate: AttributePredicate,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    alias: str | None = None,
) -> Command:
    """Filter an existing dataset in-memory by an attribute predicate, producing a new dataset.

    predicate examples:
      {"property": "type", "op": "eq", "value": "parc"}
      {"property": "longueur", "op": "gt", "value": 200}
      {"property": "type", "op": "in", "value": ["parc", "place"]}

    Operators: eq, neq, lt, gt, lte, gte, in.
    Note: 'like' (wildcard) is NOT supported here — use select_features.attribute_filter
    when you need server-side wildcard matching.

    The new dataset has lineage.parent_ids=[<source_dataset_id>].
    """
    services = get_services()
    try:
        gj = services.store.get_geojson(dataset_id)
    except FileNotFoundError:
        known = [m.id for m in services.store.list()]
        return tool_error_command(
            ToolError(
                code="dataset_not_found",
                message=f"No dataset {dataset_id}",
                suggestion=f"Available IDs: {', '.join(known) if known else '(none)'}",
            ),
            tool_call_id,
        )

    out = filter_by_attribute(gj, predicate)
    new_id = services.store.put(
        out,
        {
            "alias": alias,
            "source": {"type": "derived", "filter_summary": f"{predicate.property} {predicate.op} {predicate.value}"},
            "lineage": {
                "parent_ids": [dataset_id],
                "operation": "filter_attributes",
                "params": predicate.model_dump(),
            },
        },
    )
    meta = services.store.get_meta(new_id)
    meta_lite = DatasetMetaLite(
        id=meta.id,
        alias=meta.alias,
        feature_count=meta.feature_count,
        bbox=meta.bbox,
        layer=meta.source.layer,
        operation=meta.lineage.operation,
    )
    return dataset_created_command(
        meta_lite,
        tool_result={
            "dataset_id": new_id,
            "alias": meta.alias,
            "feature_count": meta.feature_count,
            "bbox": list(meta.bbox),
        },
        state=state,
        tool_call_id=tool_call_id,
    )
```

- [ ] **Step 4: Update existing tests in `test_tool_filter_attributes.py`**

Replace dict `predicate=` calls with `AttributePredicate(...)`:

```python
# before
result = await filter_attributes.coroutine(
    dataset_id=rid,
    predicate={"property": "longueur", "op": "gt", "value": 100},
    ...
)

# after
from geo_agent.services.spatial_ops import AttributePredicate

result = await filter_attributes.coroutine(
    dataset_id=rid,
    predicate=AttributePredicate(property="longueur", op="gt", value=100),
    ...
)
```

Drop any test that previously asserted a `bad_input` error from a malformed predicate — those are now caught upstream by args_schema.

- [ ] **Step 5: Run filter_attributes tests**

Run: `cd backend && uv run pytest tests/unit/test_tool_filter_attributes.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/geo_agent/agent/tools/filter_attributes.py backend/tests/unit/test_tool_filter_attributes.py
git commit -m "refactor(tools): type filter_attributes predicate with Pydantic"
```

---

## Task 4: Rewrite `SYSTEM_PROMPT` end-to-end

**Files:**
- Modify: `backend/geo_agent/agent/prompts.py`
- Test: `backend/tests/unit/test_prompt_builder.py` (sanity assertions only)

**Why:** Current prompt lacks `hide_on_map`, says nothing about when to use `aggregate`, gives no example for `filter_attributes` or `attribute_filter`, has no error-handling strategy, and doesn't tell the LLM to inspect attribute schemas before filtering.

- [ ] **Step 1: Read the current prompt_builder test to know what assertions exist**

```bash
cat backend/tests/unit/test_prompt_builder.py
```

- [ ] **Step 2: Add failing assertions for the new prompt content**

Append to `backend/tests/unit/test_prompt_builder.py`:

```python
def test_system_prompt_mentions_hide_on_map() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT
    assert "hide_on_map" in SYSTEM_PROMPT


def test_system_prompt_has_filter_attributes_example() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT
    # the example block uses a JSON-like literal so the LLM has a concrete shape to copy
    assert '"op": "in"' in SYSTEM_PROMPT or '"op": "gt"' in SYSTEM_PROMPT


def test_system_prompt_distinguishes_operator_sets() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT
    # the prompt must call out that 'like' is server-side only and 'in' is in-memory only
    assert "like" in SYSTEM_PROMPT and "in" in SYSTEM_PROMPT


def test_system_prompt_has_error_section() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT
    assert "too_many_features" in SYSTEM_PROMPT
    assert "dataset_not_found" in SYSTEM_PROMPT


def test_system_prompt_recommends_describe_dataset_before_filter() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT
    assert "describe_dataset" in SYSTEM_PROMPT
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_prompt_builder.py -v`
Expected: at least the `hide_on_map` and error-section assertions FAIL.

- [ ] **Step 4: Replace `SYSTEM_PROMPT` in `backend/geo_agent/agent/prompts.py`**

Full replacement content:

```python
SYSTEM_PROMPT = """# Role

You are a geospatial analysis assistant for the City of Montreal open data.
You drive a stack that fetches features from the WFS server (api.accept.montreal.ca)
and runs spatial/statistical queries.

# Core rules

1. **You never see GeoJSON.** Manipulate datasets by their `dataset_id` (e.g. `result_001`)
   and the short `alias` you assign.
2. **Every selection MUST have a geometry filter.** Either:
   - a previous `dataset_id` (typically a user drawing or a prior result), OR
   - a polygon explicitly provided in the user's message.
   Whole-layer downloads are forbidden.
3. **After producing a meaningful dataset, call `show_on_map`** so the user sees it.
4. **Always assign a short, descriptive `alias`** when creating a dataset.

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

## list_wfs_layers
Discover which WFS layers are available. Use it the first time you encounter
a topic and don't already know the layer name. Output includes `name`, `title`,
`abstract` — read the abstract before picking a layer.

## select_features
Fetch features from a WFS layer with a server-side OGC filter. Always returns
a new dataset.

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
    "geometry_source": {"type": "dataset", "dataset_id": "zone_1_id", "use_geometry": true},
    "spatial_predicate": "within",
    "attribute_filter": {"property": "type", "op": "like", "value": "parc%"},
    "alias": "parcs_dans_zone"
  }

WFS operators for `attribute_filter.op`: eq, neq, lt, gt, lte, gte, **like** (% wildcard).
**No `in`** here — see filter_attributes for that.

`use_geometry`:
  - `false` (default) → bbox of the parent dataset (fast, coarser)
  - `true` → union of all geometries (precise; only works if the union is a single Polygon)

## filter_attributes
Filter an existing dataset in-memory by an attribute predicate, producing a new dataset.
Use this when the data is already loaded and you want to slice it without re-querying.

**Before filtering: if you don't know the attribute names, call `describe_dataset`
on the source dataset to read its `attribute_schema`.**

Example — keep features above a length threshold:
  {"dataset_id": "result_003", "predicate": {"property": "longueur", "op": "gt", "value": 200}, "alias": "longues_chaussees"}

Example — keep features whose type is in a set:
  {"dataset_id": "result_003", "predicate": {"property": "type", "op": "in", "value": ["parc", "place"]}, "alias": "parcs_et_places"}

In-memory operators for `predicate.op`: eq, neq, lt, gt, lte, gte, **in** (membership).
**No `like`** here — use select_features.attribute_filter for server-side wildcard matching.

## aggregate
Compute a statistic over an existing dataset. Use this for any "how many", "what's
the average", "total length" question.

Example — count features grouped by type:
  {"dataset_id": "result_003", "op": "count", "group_by": "type"}

Example — average length:
  {"dataset_id": "result_003", "op": "mean", "attribute": "longueur"}

Ops: count (no attribute needed), sum, mean, min, max (require `attribute`).

## describe_dataset
Get full metadata for a dataset by id or alias: bbox, attribute_schema, lineage.
Geometry is never returned. Use this to discover attribute names before
`filter_attributes` or to refresh your memory.

## list_datasets
Lightweight list of all session datasets (id, alias, layer, count, bbox, operation).
The same info is already injected below — use this tool only if you need to refresh after many operations.

## show_on_map / hide_on_map
Toggle a dataset's visibility on the map. Call `show_on_map` after producing any
dataset the user should see. Call `hide_on_map` when the user asks to remove
a layer from view (the data is preserved).

# Error handling

When a tool returns an error, read the `code` and `suggestion` fields and adapt:

- `too_many_features` → refine: shrink the area, add an `attribute_filter`, or chain
  from a smaller parent dataset. Never retry the same call.
- `dataset_not_found` → check the "Current datasets" block; the `suggestion` lists
  available ids.
- `unsupported_geometry` (from `use_geometry=true` returning a MultiPolygon) →
  retry with `use_geometry=false` (bbox) or chain from a single-polygon parent.
- `bad_input` → fix the malformed argument the suggestion points to and retry once.

Never apologize about an error to the user before trying to resolve it.
"""
```

- [ ] **Step 5: Run prompt_builder tests**

Run: `cd backend && uv run pytest tests/unit/test_prompt_builder.py -v`
Expected: all assertions PASS.

- [ ] **Step 6: Run the full backend test suite to catch regressions**

Run: `cd backend && uv run pytest`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/geo_agent/agent/prompts.py backend/tests/unit/test_prompt_builder.py
git commit -m "feat(agent): rewrite SYSTEM_PROMPT with sectioned catalog, examples, error strategy"
```

---

## Task 5: Final verification

- [ ] **Step 1: Run the whole backend suite**

Run: `cd backend && uv run pytest -q`
Expected: 0 failures.

- [ ] **Step 2: Lint**

Run: `cd backend && uv run ruff check geo_agent tests`
Expected: clean.

- [ ] **Step 3: Smoke test the agent against Ollama (optional manual step)**

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
    state['messages'] = [{'role': 'user', 'content': 'List the available WFS layers about parks.'}]
    out = await agent.ainvoke(state, config={'configurable': {'thread_id': 'smoke'}})
    print(out['messages'][-1].content)

asyncio.run(main())
"
```

Expected: a response that names at least one layer and (if the LLM is decent) references the abstract.

- [ ] **Step 4: Done — no extra commit needed if everything was committed task-by-task.**

---

## Self-review checklist

- [x] Every tool flagged in the analysis has a task: `list_wfs_layers` (Task 1), `select_features` (Task 2), `filter_attributes` (Task 3), prompt (Task 4).
- [x] Operator asymmetry is documented in both tool docstrings AND the system prompt (Task 2, 3, 4).
- [x] `hide_on_map`, `aggregate` guidance, `describe_dataset` recommendation, and error strategy are all covered in the new prompt (Task 4).
- [x] No placeholders; every code block is complete.
- [x] Test-first ordering on every task.
- [x] Type names are consistent across tasks (`PolygonSource`, `DatasetSource`, `GeometrySource`, `AttributeFilterInput`, `AttributePredicate`).
