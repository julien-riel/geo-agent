# Dataset Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three agent-callable tools (`delete_dataset`, `rename_dataset`, `clear_all_datasets`), three HTTP routes for UI-driven maintenance, and a revamped bottom `DatasetPanel` with per-row delete/rename, "Tout effacer", grouping by operation type, icons, and parent-lineage indication.

**Architecture:** Tools wrap the existing `ResultStore` methods (`delete`, `update_alias`, looped delete) and emit `Command` updates so the agent state stays in sync. Parallel REST routes (`DELETE /datasets`, `DELETE /datasets/{id}`, `PATCH /datasets/{id}`) let the UI act without going through the agent. The frontend panel is rewritten to group rows by `operation` and render an emoji-icon + lineage line for derived datasets; `DatasetMetaLite` gains `parent_ids` so lineage renders without an extra fetch.

**Tech Stack:** FastAPI 0.115 + Pydantic 2, LangChain/LangGraph tools, pytest. Next.js 16 + React 19, CopilotKit 1.5, Vitest + jsdom. Local LLM via Ollama (Gemma) or OpenRouter (Claude Haiku 4.5).

**Spec:** `docs/superpowers/specs/2026-05-11-dataset-management-design.md`

---

## File Structure

### New files

```
backend/
  geo_agent/agent/tools/datasets/delete_dataset.py
  geo_agent/agent/tools/datasets/rename_dataset.py
  geo_agent/agent/tools/datasets/clear_all_datasets.py
  tests/unit/test_tool_delete_dataset.py
  tests/unit/test_tool_rename_dataset.py
  tests/unit/test_tool_clear_all_datasets.py

frontend/
  tests/unit/DatasetPanel.test.tsx
```

### Modified files

```
backend/
  geo_agent/models.py                                 # + DatasetMetaLite.parent_ids
  geo_agent/agent/tools/wfs/select_features.py        # propagate parent_ids
  geo_agent/agent/tools/datasets/filter_attributes.py # propagate parent_ids
  geo_agent/agent/tools/datasets/spatial_overlay.py   # propagate parent_ids
  geo_agent/agent/tools/datasets/spatial_join.py      # propagate parent_ids
  geo_agent/agent/tools/datasets/transform_geometry.py# propagate parent_ids
  geo_agent/agent/tools/__init__.py                   # register 3 new tools
  geo_agent/agent/prompts.py                          # system-prompt guard
  geo_agent/routes/datasets.py                        # + DELETE / DELETE-id / PATCH-id + drawing parent_ids
  tests/integration/test_datasets_route.py            # cover the 3 new routes

frontend/
  lib/types.ts                                        # + parent_ids
  app/api/datasets/route.ts                           # + DELETE handler
  app/api/datasets/[id]/route.ts                      # + DELETE / PATCH handlers
  components/GeoPage.tsx                              # hydration, onNewConversation, new callbacks
  components/DatasetPanel.tsx                         # full rewrite (groups, icons, actions, lineage)
```

---

## Task 1: Extend `DatasetMetaLite` with `parent_ids` and propagate it

**Files:**
- Modify: `backend/geo_agent/models.py:33-41`
- Modify: `backend/geo_agent/agent/tools/wfs/select_features.py:208-215`
- Modify: `backend/geo_agent/agent/tools/datasets/filter_attributes.py:62-69`
- Modify: `backend/geo_agent/agent/tools/datasets/spatial_overlay.py:18-26`
- Modify: `backend/geo_agent/agent/tools/datasets/spatial_join.py:17-25`
- Modify: `backend/geo_agent/agent/tools/datasets/transform_geometry.py:31-39`
- Modify: `backend/geo_agent/routes/datasets.py:72-79`
- Test: `backend/tests/unit/test_models.py` (add a single new test)
- Test: `backend/tests/unit/test_tool_filter_attributes.py` (extend existing test)

This is the foundation: nothing else can render lineage until every dataset-producing call site emits `parent_ids` on the lite meta.

- [ ] **Step 1: Write the failing model test**

Append to `backend/tests/unit/test_models.py`:

```python
def test_dataset_meta_lite_has_parent_ids_default_empty() -> None:
    from geo_agent.models import DatasetMetaLite

    m = DatasetMetaLite(
        id="result_001",
        alias=None,
        feature_count=1,
        bbox=(0.0, 0.0, 1.0, 1.0),
        layer=None,
        operation="user_drawing",
    )
    assert m.parent_ids == []


def test_dataset_meta_lite_accepts_parent_ids() -> None:
    from geo_agent.models import DatasetMetaLite

    m = DatasetMetaLite(
        id="result_005",
        alias="derived",
        feature_count=3,
        bbox=(0.0, 0.0, 1.0, 1.0),
        layer=None,
        operation="filter_attributes",
        parent_ids=["result_001"],
    )
    assert m.parent_ids == ["result_001"]
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend
uv run pytest tests/unit/test_models.py::test_dataset_meta_lite_has_parent_ids_default_empty -v
```

Expected: FAIL with a Pydantic `ValidationError` about an unexpected attribute, OR `AttributeError: 'DatasetMetaLite' object has no attribute 'parent_ids'`.

- [ ] **Step 3: Add `parent_ids` to `DatasetMetaLite`**

In `backend/geo_agent/models.py`, replace the existing `DatasetMetaLite` (around line 33) with:

```python
class DatasetMetaLite(BaseModel):
    """Lightweight version for the agent state — no source details."""

    id: str
    alias: str | None
    feature_count: int
    bbox: tuple[float, float, float, float]
    layer: str | None
    operation: str
    parent_ids: list[str] = Field(default_factory=list)
```

(Imports of `Field` already exist at the top of the file.)

- [ ] **Step 4: Run model tests, expect pass**

```
cd backend
uv run pytest tests/unit/test_models.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Propagate `parent_ids` in `filter_attributes`**

In `backend/geo_agent/agent/tools/datasets/filter_attributes.py`, change the `meta_lite = DatasetMetaLite(...)` block (around line 62) to:

```python
    meta_lite = DatasetMetaLite(
        id=meta.id,
        alias=meta.alias,
        feature_count=meta.feature_count,
        bbox=meta.bbox,
        layer=meta.source.layer,
        operation=meta.lineage.operation,
        parent_ids=meta.lineage.parent_ids,
    )
```

- [ ] **Step 6: Extend the filter_attributes test to assert the new field**

In `backend/tests/unit/test_tool_filter_attributes.py::test_filter_attributes_creates_new_dataset`, after the existing assertions add:

```python
    assert new_meta_lite["parent_ids"] == [populated]
```

- [ ] **Step 7: Run the filter_attributes test, expect pass**

```
cd backend
uv run pytest tests/unit/test_tool_filter_attributes.py -v
```

Expected: all tests pass.

- [ ] **Step 8: Propagate `parent_ids` in `select_features`**

In `backend/geo_agent/agent/tools/wfs/select_features.py`, change the `meta_lite = DatasetMetaLite(...)` block (around line 208) to:

```python
    meta_lite = DatasetMetaLite(
        id=meta.id,
        alias=meta.alias,
        feature_count=meta.feature_count,
        bbox=meta.bbox,
        layer=meta.source.layer,
        operation=meta.lineage.operation,
        parent_ids=meta.lineage.parent_ids,
    )
```

- [ ] **Step 9: Propagate `parent_ids` in `spatial_overlay`**

In `backend/geo_agent/agent/tools/datasets/spatial_overlay.py`, change `_meta_lite` (around line 18) to:

```python
def _meta_lite(meta) -> DatasetMetaLite:
    return DatasetMetaLite(
        id=meta.id,
        alias=meta.alias,
        feature_count=meta.feature_count,
        bbox=meta.bbox,
        layer=meta.source.layer,
        operation=meta.lineage.operation,
        parent_ids=meta.lineage.parent_ids,
    )
```

- [ ] **Step 10: Propagate `parent_ids` in `spatial_join`**

Same change as Step 9, applied to `backend/geo_agent/agent/tools/datasets/spatial_join.py::_meta_lite` (around line 17).

- [ ] **Step 11: Propagate `parent_ids` in `transform_geometry`**

Same change as Step 9, applied to `backend/geo_agent/agent/tools/datasets/transform_geometry.py::_meta_lite` (around line 31).

- [ ] **Step 12: Include `parent_ids` in `create_drawing`'s response**

In `backend/geo_agent/routes/datasets.py`, change the `create_drawing` return dict (around line 72) to:

```python
    return {
        "id": rid,
        "alias": meta.alias,
        "feature_count": meta.feature_count,
        "bbox": list(meta.bbox),
        "layer": None,
        "operation": "user_drawing",
        "parent_ids": [],
    }
```

- [ ] **Step 13: Run the full backend test suite**

```
cd backend
uv run pytest -q
```

Expected: all tests pass. (The other producing-tool tests do not yet assert `parent_ids` — adding `parent_ids` with a default factory is a backward-compatible change.)

- [ ] **Step 14: Commit**

```bash
git add backend/geo_agent/models.py \
        backend/geo_agent/agent/tools/wfs/select_features.py \
        backend/geo_agent/agent/tools/datasets/filter_attributes.py \
        backend/geo_agent/agent/tools/datasets/spatial_overlay.py \
        backend/geo_agent/agent/tools/datasets/spatial_join.py \
        backend/geo_agent/agent/tools/datasets/transform_geometry.py \
        backend/geo_agent/routes/datasets.py \
        backend/tests/unit/test_models.py \
        backend/tests/unit/test_tool_filter_attributes.py
git commit -m "feat(models): add parent_ids to DatasetMetaLite, propagate from all producing tools"
```

---

## Task 2: `delete_dataset` tool

**Files:**
- Create: `backend/geo_agent/agent/tools/datasets/delete_dataset.py`
- Create: `backend/tests/unit/test_tool_delete_dataset.py`

- [ ] **Step 1: Write the test file**

Create `backend/tests/unit/test_tool_delete_dataset.py`:

```python
from pathlib import Path

import pytest
from langgraph.types import Command

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.delete_dataset import delete_dataset
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.delete_dataset.get_services", lambda: services)
    return services


def _put(services: Services, alias: str | None = None) -> str:
    return services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}]},
        {"alias": alias, "source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select_features", "params": {}}},
    )


async def test_delete_dataset_removes_files_and_state(services: Services) -> None:
    rid_keep = _put(services)
    rid_drop = _put(services)
    state = {"datasets": [{"id": rid_keep}, {"id": rid_drop}], "active_layers": [rid_drop, rid_keep]}

    result = await delete_dataset.coroutine(id_or_alias=rid_drop, state=state, tool_call_id="t")

    assert isinstance(result, Command)
    assert [d["id"] for d in result.update["datasets"]] == [rid_keep]
    assert result.update["active_layers"] == [rid_keep]
    # Store side-effect: the dropped dataset is gone, the kept one survives.
    with pytest.raises(FileNotFoundError):
        services.store.get_meta(rid_drop)
    assert services.store.get_meta(rid_keep).id == rid_keep


async def test_delete_dataset_accepts_alias(services: Services) -> None:
    rid = _put(services, alias="park")
    state = {"datasets": [{"id": rid}], "active_layers": []}

    result = await delete_dataset.coroutine(id_or_alias="park", state=state, tool_call_id="t")

    assert result.update["datasets"] == []
    with pytest.raises(FileNotFoundError):
        services.store.get_meta(rid)


async def test_delete_dataset_missing_returns_dataset_not_found(services: Services) -> None:
    state = {"datasets": [], "active_layers": []}

    result = await delete_dataset.coroutine(id_or_alias="result_999", state=state, tool_call_id="t")

    assert result.update["errors"][0]["code"] == "dataset_not_found"
    assert "datasets" not in result.update
    assert "active_layers" not in result.update
```

- [ ] **Step 2: Run the tests, expect ImportError**

```
cd backend
uv run pytest tests/unit/test_tool_delete_dataset.py -v
```

Expected: collection error (module not found).

- [ ] **Step 3: Implement `delete_dataset`**

Create `backend/geo_agent/agent/tools/datasets/delete_dataset.py`:

```python
import json
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from geo_agent.agent.error_helpers import dataset_not_found_command
from geo_agent.agent.registry import get_services


@tool
async def delete_dataset(
    id_or_alias: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Delete a dataset (by id or alias) from the local store.

    Removes the dataset's geometry and metadata files, drops it from the visible map layers,
    and updates the session's dataset list. Downstream datasets that referenced it through
    lineage are NOT cascaded — they remain with a now-dangling parent id.
    """
    services = get_services()
    try:
        rid = services.store._resolve_id(id_or_alias)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, id_or_alias, tool_call_id)

    services.store.delete(rid)

    new_datasets = [d for d in (state.get("datasets") or []) if d.get("id") != rid]
    new_active = [x for x in (state.get("active_layers") or []) if x != rid]

    return Command(
        update={
            "datasets": new_datasets,
            "active_layers": new_active,
            "messages": [
                ToolMessage(content=json.dumps({"deleted": rid}), tool_call_id=tool_call_id),
            ],
        }
    )
```

- [ ] **Step 4: Run the tests, expect pass**

```
cd backend
uv run pytest tests/unit/test_tool_delete_dataset.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/agent/tools/datasets/delete_dataset.py \
        backend/tests/unit/test_tool_delete_dataset.py
git commit -m "feat(tools): add delete_dataset agent tool"
```

---

## Task 3: `rename_dataset` tool

**Files:**
- Create: `backend/geo_agent/agent/tools/datasets/rename_dataset.py`
- Create: `backend/tests/unit/test_tool_rename_dataset.py`

- [ ] **Step 1: Write the test file**

Create `backend/tests/unit/test_tool_rename_dataset.py`:

```python
from pathlib import Path

import pytest
from langgraph.types import Command

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.rename_dataset import rename_dataset
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.rename_dataset.get_services", lambda: services)
    return services


def _put(services: Services, alias: str | None = None) -> str:
    return services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}]},
        {"alias": alias, "source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select_features", "params": {}}},
    )


async def test_rename_dataset_updates_alias(services: Services) -> None:
    rid = _put(services)
    state = {"datasets": [{"id": rid, "alias": None}]}

    result = await rename_dataset.coroutine(
        id_or_alias=rid, new_alias="park", state=state, tool_call_id="t"
    )

    assert isinstance(result, Command)
    assert services.store.get_meta(rid).alias == "park"
    assert result.update["datasets"][0]["alias"] == "park"


async def test_rename_dataset_rejects_whitespace(services: Services) -> None:
    rid = _put(services)
    state = {"datasets": [{"id": rid, "alias": None}]}

    result = await rename_dataset.coroutine(
        id_or_alias=rid, new_alias="bad name", state=state, tool_call_id="t"
    )

    assert result.update["errors"][0]["code"] == "bad_input"
    assert "datasets" not in result.update


async def test_rename_dataset_rejects_empty(services: Services) -> None:
    rid = _put(services)
    state = {"datasets": [{"id": rid, "alias": None}]}

    result = await rename_dataset.coroutine(
        id_or_alias=rid, new_alias="", state=state, tool_call_id="t"
    )

    assert result.update["errors"][0]["code"] == "bad_input"


async def test_rename_dataset_rejects_too_long(services: Services) -> None:
    rid = _put(services)
    state = {"datasets": [{"id": rid, "alias": None}]}

    result = await rename_dataset.coroutine(
        id_or_alias=rid, new_alias="x" * 65, state=state, tool_call_id="t"
    )

    assert result.update["errors"][0]["code"] == "bad_input"


async def test_rename_dataset_detects_alias_conflict(services: Services) -> None:
    rid_keep = _put(services, alias="park")
    rid_other = _put(services)
    state = {"datasets": [{"id": rid_keep, "alias": "park"}, {"id": rid_other, "alias": None}]}

    result = await rename_dataset.coroutine(
        id_or_alias=rid_other, new_alias="park", state=state, tool_call_id="t"
    )

    assert result.update["errors"][0]["code"] == "alias_conflict"
    assert services.store.get_meta(rid_other).alias is None


async def test_rename_dataset_same_alias_noop(services: Services) -> None:
    rid = _put(services, alias="park")
    state = {"datasets": [{"id": rid, "alias": "park"}]}

    result = await rename_dataset.coroutine(
        id_or_alias=rid, new_alias="park", state=state, tool_call_id="t"
    )

    # No error and the meta is unchanged.
    assert "errors" not in result.update
    assert services.store.get_meta(rid).alias == "park"


async def test_rename_dataset_missing_returns_dataset_not_found(services: Services) -> None:
    state = {"datasets": []}

    result = await rename_dataset.coroutine(
        id_or_alias="result_999", new_alias="park", state=state, tool_call_id="t"
    )

    assert result.update["errors"][0]["code"] == "dataset_not_found"
```

- [ ] **Step 2: Run the tests, expect ImportError**

```
cd backend
uv run pytest tests/unit/test_tool_rename_dataset.py -v
```

Expected: collection error.

- [ ] **Step 3: Implement `rename_dataset`**

Create `backend/geo_agent/agent/tools/datasets/rename_dataset.py`:

```python
import json
import re
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from geo_agent.agent.error_helpers import dataset_not_found_command, tool_error_command
from geo_agent.agent.registry import get_services
from geo_agent.models import ToolError

_ALIAS_RE = re.compile(r"^\S{1,64}$")


@tool
async def rename_dataset(
    id_or_alias: str,
    new_alias: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Set or change a dataset's short human-readable alias.

    The alias must be non-empty, contain no whitespace, and be at most 64 characters.
    Aliases must be unique across the session.
    """
    services = get_services()

    if not _ALIAS_RE.match(new_alias or ""):
        return tool_error_command(
            ToolError(
                code="bad_input",
                message=f"Invalid alias {new_alias!r}",
                suggestion="alias must be non-empty, contain no whitespace, and be at most 64 characters",
            ),
            tool_call_id,
        )

    try:
        rid = services.store._resolve_id(id_or_alias)
    except FileNotFoundError:
        return dataset_not_found_command(services.store, id_or_alias, tool_call_id)

    for m in services.store.list():
        if m.id != rid and m.alias == new_alias:
            return tool_error_command(
                ToolError(
                    code="alias_conflict",
                    message=f"Alias {new_alias!r} already in use",
                    suggestion=f"alias '{new_alias}' is already used by {m.id}; pick another",
                ),
                tool_call_id,
            )

    services.store.update_alias(rid, new_alias)

    new_datasets = []
    for d in state.get("datasets") or []:
        if d.get("id") == rid:
            new_datasets.append({**d, "alias": new_alias})
        else:
            new_datasets.append(d)

    return Command(
        update={
            "datasets": new_datasets,
            "messages": [
                ToolMessage(
                    content=json.dumps({"id": rid, "alias": new_alias}),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
```

- [ ] **Step 4: Run the tests, expect pass**

```
cd backend
uv run pytest tests/unit/test_tool_rename_dataset.py -v
```

Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/agent/tools/datasets/rename_dataset.py \
        backend/tests/unit/test_tool_rename_dataset.py
git commit -m "feat(tools): add rename_dataset agent tool (with alias_conflict error)"
```

---

## Task 4: `clear_all_datasets` tool

**Files:**
- Create: `backend/geo_agent/agent/tools/datasets/clear_all_datasets.py`
- Create: `backend/tests/unit/test_tool_clear_all_datasets.py`

- [ ] **Step 1: Write the test file**

Create `backend/tests/unit/test_tool_clear_all_datasets.py`:

```python
from pathlib import Path

import pytest
from langgraph.types import Command

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.datasets.clear_all_datasets import clear_all_datasets
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    services = Services(settings=settings, wfs=None, store=FileSystemResultStore(data_dir=data_dir))  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.datasets.clear_all_datasets.get_services", lambda: services)
    return services


def _put(services: Services) -> str:
    return services.store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}]},
        {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select_features", "params": {}}},
    )


async def test_clear_all_datasets_removes_everything(services: Services) -> None:
    _put(services)
    _put(services)
    _put(services)
    state = {"datasets": [{"id": "result_001"}, {"id": "result_002"}, {"id": "result_003"}], "active_layers": ["result_001", "result_002"]}

    result = await clear_all_datasets.coroutine(state=state, tool_call_id="t")

    assert isinstance(result, Command)
    assert result.update["datasets"] == []
    assert result.update["active_layers"] == []
    assert services.store.list() == []


async def test_clear_all_datasets_is_idempotent_on_empty_store(services: Services) -> None:
    state = {"datasets": [], "active_layers": []}

    result = await clear_all_datasets.coroutine(state=state, tool_call_id="t")

    assert result.update["datasets"] == []
    assert result.update["active_layers"] == []
    assert "errors" not in result.update
```

- [ ] **Step 2: Run the tests, expect ImportError**

```
cd backend
uv run pytest tests/unit/test_tool_clear_all_datasets.py -v
```

Expected: collection error.

- [ ] **Step 3: Implement `clear_all_datasets`**

Create `backend/geo_agent/agent/tools/datasets/clear_all_datasets.py`:

```python
import json
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from geo_agent.agent.registry import get_services


@tool
async def clear_all_datasets(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Delete every dataset in the current session — destructive and irreversible.

    Only call this when the user explicitly asks to start over (e.g. "efface tous les datasets",
    "repars de zéro"). Do not call it on your own initiative.
    """
    services = get_services()
    count = 0
    for m in services.store.list():
        services.store.delete(m.id)
        count += 1

    return Command(
        update={
            "datasets": [],
            "active_layers": [],
            "messages": [
                ToolMessage(content=json.dumps({"deleted": count}), tool_call_id=tool_call_id),
            ],
        }
    )
```

- [ ] **Step 4: Run the tests, expect pass**

```
cd backend
uv run pytest tests/unit/test_tool_clear_all_datasets.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/agent/tools/datasets/clear_all_datasets.py \
        backend/tests/unit/test_tool_clear_all_datasets.py
git commit -m "feat(tools): add clear_all_datasets agent tool"
```

---

## Task 5: Register tools in `ALL_TOOLS` and add the system-prompt guard

**Files:**
- Modify: `backend/geo_agent/agent/tools/__init__.py`
- Modify: `backend/geo_agent/agent/prompts.py:36-191`
- Test: `backend/tests/unit/test_tools_package.py` (extend)

- [ ] **Step 1: Read the existing tools-package test to learn the assertion style**

```
cat backend/tests/unit/test_tools_package.py
```

The test enumerates `ALL_TOOLS` names. We will extend it.

- [ ] **Step 2: Add the new tools to `ALL_TOOLS` and `__all__`**

In `backend/geo_agent/agent/tools/__init__.py`, replace the three import + listing blocks so the file reads:

```python
from geo_agent.agent.tools.datasets.aggregate import aggregate
from geo_agent.agent.tools.datasets.clear_all_datasets import clear_all_datasets
from geo_agent.agent.tools.datasets.delete_dataset import delete_dataset
from geo_agent.agent.tools.datasets.describe_dataset import describe_dataset
from geo_agent.agent.tools.datasets.filter_attributes import filter_attributes
from geo_agent.agent.tools.datasets.rename_dataset import rename_dataset
from geo_agent.agent.tools.datasets.spatial_join import spatial_join
from geo_agent.agent.tools.datasets.spatial_overlay import spatial_overlay
from geo_agent.agent.tools.datasets.transform_geometry import transform_geometry
from geo_agent.agent.tools.ui.inspect_dataset import inspect_dataset
from geo_agent.agent.tools.ui.show_on_map import hide_on_map, show_on_map
from geo_agent.agent.tools.wfs.describe_layer import describe_wfs_layer
from geo_agent.agent.tools.wfs.list_layers import list_wfs_layers
from geo_agent.agent.tools.wfs.select_features import select_features

# NOTE: `list_datasets` is intentionally NOT registered here. The same metadata is
# re-injected into the system prompt on every model turn (see prompt_builder), so a
# dedicated tool would only be a distractor for the (small, local) model. The function
# still exists in datasets/list_datasets.py and is exercised by its own unit test.
ALL_TOOLS = [
    # WFS server tools
    list_wfs_layers,
    describe_wfs_layer,
    select_features,
    # Local dataset tools
    filter_attributes,
    aggregate,
    describe_dataset,
    spatial_overlay,
    spatial_join,
    transform_geometry,
    # Local dataset management
    delete_dataset,
    rename_dataset,
    clear_all_datasets,
    # UI tools
    show_on_map,
    hide_on_map,
    inspect_dataset,
]

__all__ = [
    "ALL_TOOLS",
    "list_wfs_layers",
    "describe_wfs_layer",
    "select_features",
    "filter_attributes",
    "aggregate",
    "describe_dataset",
    "spatial_join",
    "spatial_overlay",
    "transform_geometry",
    "delete_dataset",
    "rename_dataset",
    "clear_all_datasets",
    "show_on_map",
    "hide_on_map",
    "inspect_dataset",
]
```

- [ ] **Step 3: Extend the tools-package test**

In `backend/tests/unit/test_tools_package.py`, find the assertion that enumerates tool names and add `"delete_dataset"`, `"rename_dataset"`, `"clear_all_datasets"` to the expected list. If the file checks the length, bump it from 12 to 15.

- [ ] **Step 4: Run the tools-package test, expect pass**

```
cd backend
uv run pytest tests/unit/test_tools_package.py -v
```

Expected: pass.

- [ ] **Step 5: Add the system-prompt guard**

In `backend/geo_agent/agent/prompts.py`, in the "Local dataset tools" subsection, after the `### describe_dataset` block (around line 165, before the `## UI tools` heading), add:

```
### delete_dataset / rename_dataset / clear_all_datasets
Maintenance over the session's datasets.

`delete_dataset` removes one dataset (by id or alias). `rename_dataset` sets or changes a dataset's
short alias — the alias must be non-empty, contain no whitespace, and be unique within the session.

**`clear_all_datasets` est destructif et irréversible.** Ne l'appelle **jamais** sans une demande
explicite de l'utilisateur (ex. « efface tous les datasets », « repars de zéro »). En cas de doute,
demande confirmation par message — n'appelle pas le tool.

Examples:
  {"id_or_alias": "result_005"}                          # delete_dataset
  {"id_or_alias": "result_003", "new_alias": "parcs"}    # rename_dataset
  {}                                                      # clear_all_datasets
```

- [ ] **Step 6: Extend the "Choosing the right tool" mapping**

In `backend/geo_agent/agent/prompts.py`, in the "# Choosing the right tool" section, append these bullets (just before "When in doubt…"):

```
- "supprime / efface / enlève le dataset X" → `delete_dataset`
- "renomme X en Y" / "appelle X 'foo'" → `rename_dataset`
- "efface tous les datasets / repars de zéro" → `clear_all_datasets` (demande confirmation d'abord
  si la demande n'est pas explicite)
```

- [ ] **Step 7: Sanity-check the prompt builder still composes**

```
cd backend
uv run pytest tests/unit/test_prompt_builder.py -v
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add backend/geo_agent/agent/tools/__init__.py \
        backend/geo_agent/agent/prompts.py \
        backend/tests/unit/test_tools_package.py
git commit -m "feat(agent): register dataset-management tools and add destructive-action guard"
```

---

## Task 6: `DELETE /datasets` route (bulk clear)

**Files:**
- Modify: `backend/geo_agent/routes/datasets.py`
- Modify: `backend/tests/integration/test_datasets_route.py`

- [ ] **Step 1: Write the failing integration test**

Append to `backend/tests/integration/test_datasets_route.py`:

```python
def test_delete_all_datasets(client, tmp_path: Path) -> None:
    _put_dataset(tmp_path)
    _put_dataset(tmp_path)

    r = client.delete("/datasets")

    assert r.status_code == 200
    assert r.json() == {"deleted": 2}
    assert client.get("/datasets").json() == []


def test_delete_all_datasets_on_empty_store(client) -> None:
    r = client.delete("/datasets")
    assert r.status_code == 200
    assert r.json() == {"deleted": 0}
```

- [ ] **Step 2: Run, expect failure**

```
cd backend
uv run pytest tests/integration/test_datasets_route.py::test_delete_all_datasets -v
```

Expected: FAIL with 405 (method not allowed).

- [ ] **Step 3: Add the route**

In `backend/geo_agent/routes/datasets.py`, after the existing `create_drawing` function, append:

```python
@router.delete("")
def clear_all() -> dict:
    services = get_services()
    ids = [m.id for m in services.store.list()]
    for i in ids:
        services.store.delete(i)
    return {"deleted": len(ids)}
```

- [ ] **Step 4: Run, expect pass**

```
cd backend
uv run pytest tests/integration/test_datasets_route.py::test_delete_all_datasets tests/integration/test_datasets_route.py::test_delete_all_datasets_on_empty_store -v
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/routes/datasets.py \
        backend/tests/integration/test_datasets_route.py
git commit -m "feat(api): DELETE /datasets clears the store"
```

---

## Task 7: `DELETE /datasets/{id}` route

**Files:**
- Modify: `backend/geo_agent/routes/datasets.py`
- Modify: `backend/tests/integration/test_datasets_route.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/integration/test_datasets_route.py`:

```python
def test_delete_dataset_by_id(client, tmp_path: Path) -> None:
    rid_keep = _put_dataset(tmp_path)
    rid_drop = _put_dataset(tmp_path)

    r = client.delete(f"/datasets/{rid_drop}")

    assert r.status_code == 200
    assert r.json() == {"deleted": rid_drop}
    listed = {row["id"] for row in client.get("/datasets").json()}
    assert listed == {rid_keep}


def test_delete_dataset_unknown_id_404(client) -> None:
    r = client.delete("/datasets/result_999")
    assert r.status_code == 404
```

- [ ] **Step 2: Run, expect failure**

```
cd backend
uv run pytest tests/integration/test_datasets_route.py::test_delete_dataset_by_id -v
```

Expected: FAIL with 405 or routing mismatch.

- [ ] **Step 3: Add the route**

In `backend/geo_agent/routes/datasets.py`, after the new `clear_all` function, append:

```python
@router.delete("/{dataset_id}")
def delete_one(dataset_id: str) -> dict:
    services = get_services()
    try:
        services.store.delete(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset {dataset_id} not found")
    return {"deleted": dataset_id}
```

- [ ] **Step 4: Run the new tests, expect pass**

```
cd backend
uv run pytest tests/integration/test_datasets_route.py::test_delete_dataset_by_id tests/integration/test_datasets_route.py::test_delete_dataset_unknown_id_404 -v
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/routes/datasets.py \
        backend/tests/integration/test_datasets_route.py
git commit -m "feat(api): DELETE /datasets/{id} removes a single dataset"
```

---

## Task 8: `PATCH /datasets/{id}` route (rename)

**Files:**
- Modify: `backend/geo_agent/routes/datasets.py`
- Modify: `backend/tests/integration/test_datasets_route.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/integration/test_datasets_route.py`:

```python
def _put_named(tmp_path: Path, alias: str | None) -> str:
    from geo_agent.config import Settings
    from geo_agent.services.result_store import FileSystemResultStore

    s = Settings()
    store = FileSystemResultStore(data_dir=s.DATA_DIR)
    return store.put(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}]},
        {"alias": alias, "source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select_features", "params": {}}},
    )


def test_patch_dataset_renames_alias(client, tmp_path: Path) -> None:
    rid = _put_named(tmp_path, alias=None)

    r = client.patch(f"/datasets/{rid}", json={"alias": "park"})

    assert r.status_code == 200, r.text
    assert r.json() == {"id": rid, "alias": "park"}
    assert client.get(f"/datasets/{rid}/meta").json()["alias"] == "park"


def test_patch_dataset_rejects_invalid_alias(client, tmp_path: Path) -> None:
    rid = _put_named(tmp_path, alias=None)

    r = client.patch(f"/datasets/{rid}", json={"alias": "bad name"})

    assert r.status_code == 400


def test_patch_dataset_rejects_empty_alias(client, tmp_path: Path) -> None:
    rid = _put_named(tmp_path, alias=None)

    r = client.patch(f"/datasets/{rid}", json={"alias": ""})

    assert r.status_code == 400


def test_patch_dataset_detects_collision(client, tmp_path: Path) -> None:
    _put_named(tmp_path, alias="park")
    rid_other = _put_named(tmp_path, alias=None)

    r = client.patch(f"/datasets/{rid_other}", json={"alias": "park"})

    assert r.status_code == 409


def test_patch_dataset_unknown_id_404(client) -> None:
    r = client.patch("/datasets/result_999", json={"alias": "park"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run, expect failure**

```
cd backend
uv run pytest tests/integration/test_datasets_route.py::test_patch_dataset_renames_alias -v
```

Expected: FAIL with 405.

- [ ] **Step 3: Add the route**

In `backend/geo_agent/routes/datasets.py`, append to the existing `class DrawingPayload(BaseModel):` block area — keep `DrawingPayload` as-is — and add immediately after it:

```python
class AliasPayload(BaseModel):
    alias: str
```

Then append a new endpoint after `delete_one`:

```python
@router.patch("/{dataset_id}")
def rename(dataset_id: str, payload: AliasPayload) -> dict:
    services = get_services()
    new_alias = payload.alias
    if (
        not new_alias
        or any(c.isspace() for c in new_alias)
        or len(new_alias) > 64
    ):
        raise HTTPException(
            400,
            "alias must be non-empty, contain no whitespace, and be at most 64 chars",
        )
    try:
        rid = services.store._resolve_id(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset {dataset_id} not found")
    for m in services.store.list():
        if m.id != rid and m.alias == new_alias:
            raise HTTPException(409, f"alias '{new_alias}' already used by {m.id}")
    services.store.update_alias(rid, new_alias)
    return {"id": rid, "alias": new_alias}
```

- [ ] **Step 4: Run all new tests, expect pass**

```
cd backend
uv run pytest tests/integration/test_datasets_route.py -v
```

Expected: every test passes (existing + 5 new).

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/routes/datasets.py \
        backend/tests/integration/test_datasets_route.py
git commit -m "feat(api): PATCH /datasets/{id} renames a dataset's alias"
```

---

## Task 9: Frontend types — `parent_ids` on `DatasetMetaLite`

**Files:**
- Modify: `frontend/lib/types.ts:3-11`

- [ ] **Step 1: Update the zod schema**

In `frontend/lib/types.ts`, replace lines 3–11 (the `DatasetMetaLite` schema) with:

```ts
export const DatasetMetaLite = z.object({
  id: z.string(),
  alias: z.string().nullable(),
  feature_count: z.number(),
  bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  layer: z.string().nullable(),
  operation: z.string(),
  parent_ids: z.array(z.string()).default([]),
});
export type DatasetMetaLite = z.infer<typeof DatasetMetaLite>;
```

- [ ] **Step 2: Type-check**

```
cd frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts
git commit -m "feat(types): add parent_ids to DatasetMetaLite"
```

---

## Task 10: Frontend API proxies — DELETE on `/datasets` and DELETE/PATCH on `/datasets/[id]`

**Files:**
- Modify: `frontend/app/api/datasets/route.ts`
- Modify: `frontend/app/api/datasets/[id]/route.ts`

- [ ] **Step 1: Add DELETE to `/api/datasets`**

Replace `frontend/app/api/datasets/route.ts` with:

```ts
import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(_req: NextRequest) {
  const r = await fetch(`${BACKEND_URL}/datasets`);
  if (!r.ok) return new Response("upstream error", { status: 502 });
  const body = await r.text();
  return new Response(body, {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

export async function DELETE(_req: NextRequest) {
  const r = await fetch(`${BACKEND_URL}/datasets`, { method: "DELETE" });
  return new Response(await r.text(), {
    status: r.status,
    headers: { "content-type": "application/json" },
  });
}
```

- [ ] **Step 2: Add DELETE and PATCH to `/api/datasets/[id]`**

Replace `frontend/app/api/datasets/[id]/route.ts` with:

```ts
import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const r = await fetch(`${BACKEND_URL}/datasets/${id}/geojson`);
  if (!r.ok) return new Response("not found", { status: 404 });
  const body = await r.text();
  return new Response(body, {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

export async function DELETE(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const r = await fetch(`${BACKEND_URL}/datasets/${id}`, { method: "DELETE" });
  return new Response(await r.text(), {
    status: r.status,
    headers: { "content-type": "application/json" },
  });
}

export async function PATCH(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const body = await req.text();
  const r = await fetch(`${BACKEND_URL}/datasets/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body,
  });
  return new Response(await r.text(), {
    status: r.status,
    headers: { "content-type": "application/json" },
  });
}
```

- [ ] **Step 3: Type-check**

```
cd frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/api/datasets/route.ts frontend/app/api/datasets/[id]/route.ts
git commit -m "feat(api): proxy DELETE and PATCH for dataset management"
```

---

## Task 11: `GeoPage.tsx` — hydration, `onNewConversation`, new callbacks

**Files:**
- Modify: `frontend/components/GeoPage.tsx`

This task adds the wiring the new `DatasetPanel` will consume in Task 12. The panel signature changes; the new props are introduced here.

- [ ] **Step 1: Pass `parent_ids` on hydration**

In `frontend/components/GeoPage.tsx`, in the hydration effect (around line 87), replace the inner mapping:

```tsx
        setHydratedDatasets(
          rows.map((m) => ({
            id: m.id,
            alias: m.alias,
            feature_count: m.feature_count,
            bbox: m.bbox,
            layer: m.source?.layer ?? null,
            operation: m.lineage?.operation ?? "unknown",
            parent_ids: m.lineage?.parent_ids ?? [],
          }))
        );
```

Update the `rows` type annotation in the same `.then` to include `lineage: { operation: string; parent_ids: string[] }`:

```tsx
.then((rows: Array<{ id: string; alias: string | null; feature_count: number; bbox: [number, number, number, number]; source: { layer: string | null }; lineage: { operation: string; parent_ids: string[] } }>) => {
```

- [ ] **Step 2: Update `onNewConversation` to clear datasets first**

Replace the existing `onNewConversation` (around line 237) with:

```tsx
  const onNewConversation = async () => {
    if (!window.confirm("Effacer la conversation et tous les datasets ?")) return;
    try {
      await fetch("/api/datasets", { method: "DELETE" });
    } catch (e) {
      console.error("clear datasets failed", e);
    }
    resetThreadId();
    window.location.reload();
  };
```

- [ ] **Step 3: Add `onClearDatasets`** (the `DatasetPanel` owns the confirm dialog — Task 12)

Just below `onNewConversation`, add:

```tsx
  const onClearDatasets = async () => {
    try {
      const r = await fetch("/api/datasets", { method: "DELETE" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const current = agentState ?? EMPTY_STATE;
      setAgentState({ ...current, datasets: [], active_layers: [] });
    } catch (e) {
      console.error("clear datasets failed", e);
    }
  };
```

- [ ] **Step 4: Add `onDeleteDataset`** (the `DatasetPanel` owns the confirm dialog — Task 12)

Below `onClearDatasets`, add:

```tsx
  const onDeleteDataset = async (id: string) => {
    try {
      const r = await fetch(`/api/datasets/${id}`, { method: "DELETE" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const current = agentState ?? EMPTY_STATE;
      setAgentState({
        ...current,
        datasets: current.datasets.filter((d) => d.id !== id),
        active_layers: current.active_layers.filter((x) => x !== id),
      });
    } catch (e) {
      console.error("delete dataset failed", e);
    }
  };
```

- [ ] **Step 5: Add `onRenameDataset`**

Below `onDeleteDataset`, add:

```tsx
  const onRenameDataset = async (id: string, newAlias: string): Promise<string | null> => {
    try {
      const r = await fetch(`/api/datasets/${id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ alias: newAlias }),
      });
      if (!r.ok) {
        try {
          const payload = (await r.json()) as { detail?: string };
          return payload.detail ?? `HTTP ${r.status}`;
        } catch {
          return `HTTP ${r.status}`;
        }
      }
      const current = agentState ?? EMPTY_STATE;
      setAgentState({
        ...current,
        datasets: current.datasets.map((d) => (d.id === id ? { ...d, alias: newAlias } : d)),
      });
      return null;
    } catch (e) {
      console.error("rename dataset failed", e);
      return "network error";
    }
  };
```

(Return `null` on success, an error string on failure — the panel uses this to surface the inline message.)

- [ ] **Step 6: Pass the new callbacks to `DatasetPanel`**

In the JSX (around line 266), replace the `<DatasetPanel ... />` block with:

```tsx
        <DatasetPanel
          datasets={datasets}
          activeLayers={activeLayers}
          onToggle={onToggle}
          onDraw={onDraw}
          drawingActive={drawing}
          onClearAll={onClearDatasets}
          onDelete={onDeleteDataset}
          onRename={onRenameDataset}
        />
```

(`DatasetPanel` does not yet declare these props — TypeScript will fail until Task 12 ships. That's expected; do not run `tsc` between steps yet.)

- [ ] **Step 7: Commit (with a known typecheck break that Task 12 fixes)**

```bash
git add frontend/components/GeoPage.tsx
git commit -m "feat(GeoPage): wire dataset-management callbacks (panel rewrite follows)"
```

---

## Task 12: `DatasetPanel.tsx` — rewrite with groups, icons, actions, lineage

**Files:**
- Modify: `frontend/components/DatasetPanel.tsx`

This rewrite consumes the new props from Task 11. Tests come in Task 13.

- [ ] **Step 1: Replace the file**

Replace `frontend/components/DatasetPanel.tsx` entirely with:

```tsx
"use client";

import { useState } from "react";

import { DatasetMetaLite } from "@/lib/types";

interface Props {
  datasets: DatasetMetaLite[];
  activeLayers: string[];
  onToggle: (id: string) => void;
  onDraw: () => void;
  drawingActive: boolean;
  onClearAll: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, newAlias: string) => Promise<string | null>;
}

const OP_ICONS: Record<string, string> = {
  user_drawing: "📐",
  select_features: "🌐",
  filter_attributes: "🔍",
  aggregate: "Σ",
  spatial_overlay: "⧉",
  spatial_join: "⊕",
  transform_geometry: "↻",
};

function opIcon(op: string): string {
  return OP_ICONS[op] ?? "•";
}

type GroupKey = "zones" | "wfs" | "derived";

function groupKey(op: string): GroupKey {
  if (op === "user_drawing") return "zones";
  if (op === "select_features") return "wfs";
  return "derived";
}

const GROUP_TITLES: Record<GroupKey, string> = {
  zones: "Zones dessinées",
  wfs: "Résultats WFS",
  derived: "Dérivés",
};

const GROUP_ORDER: GroupKey[] = ["zones", "wfs", "derived"];

function groupDatasets(datasets: DatasetMetaLite[]): Record<GroupKey, DatasetMetaLite[]> {
  const out: Record<GroupKey, DatasetMetaLite[]> = { zones: [], wfs: [], derived: [] };
  for (const d of datasets) out[groupKey(d.operation)].push(d);
  for (const k of GROUP_ORDER) out[k].sort((a, b) => a.id.localeCompare(b.id));
  return out;
}

function ParentLineage({ parentIds, datasets }: { parentIds: string[]; datasets: DatasetMetaLite[] }) {
  if (parentIds.length === 0) return null;
  return (
    <div style={{ fontStyle: "italic", fontSize: 12, color: "#666", marginLeft: 28 }}>
      ←{" "}
      {parentIds.map((pid, i) => {
        const parent = datasets.find((d) => d.id === pid);
        const label = parent?.alias ?? pid;
        const isOrphan = !parent;
        return (
          <span key={pid}>
            {i > 0 && ", "}
            <span style={isOrphan ? { textDecoration: "line-through" } : undefined}>{label}</span>
          </span>
        );
      })}
    </div>
  );
}

function DatasetRow({
  d,
  visible,
  datasets,
  onToggle,
  onDelete,
  onRename,
}: {
  d: DatasetMetaLite;
  visible: boolean;
  datasets: DatasetMetaLite[];
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, newAlias: string) => Promise<string | null>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(d.alias ?? "");
  const [error, setError] = useState<string | null>(null);

  const isValidAlias = (s: string) => /^\S{1,64}$/.test(s);

  const submit = async () => {
    const trimmed = draft;
    if (trimmed === (d.alias ?? "")) {
      setEditing(false);
      setError(null);
      return;
    }
    if (!isValidAlias(trimmed)) {
      setError("non vide, sans espaces, max 64 caractères");
      return;
    }
    const err = await onRename(d.id, trimmed);
    if (err) {
      setError(err);
      return;
    }
    setEditing(false);
    setError(null);
  };

  return (
    <li style={{ padding: "4px 0", borderBottom: "1px dotted #eee" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <input
          type="checkbox"
          checked={visible}
          onChange={() => onToggle(d.id)}
          aria-label={`afficher ${d.alias ?? d.id}`}
        />
        <span aria-label={d.operation} title={d.operation}>
          {opIcon(d.operation)}
        </span>
        {editing ? (
          <input
            autoFocus
            value={draft}
            maxLength={64}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
              if (e.key === "Escape") {
                setEditing(false);
                setDraft(d.alias ?? "");
                setError(null);
              }
            }}
            onBlur={submit}
            style={{ flex: "0 1 200px" }}
            aria-label="nouvel alias"
          />
        ) : (
          <strong>{d.alias ?? d.id}</strong>
        )}
        <span style={{ color: "#666", flex: 1 }}>
          {d.feature_count} features
          {d.layer ? ` · ${d.layer}` : ""}
        </span>
        <button
          aria-label={`renommer ${d.alias ?? d.id}`}
          title="Renommer"
          onClick={() => {
            setEditing(true);
            setDraft(d.alias ?? "");
            setError(null);
          }}
          style={{ background: "transparent", border: 0, cursor: "pointer", fontSize: 14 }}
        >
          ✎
        </button>
        <button
          aria-label={`supprimer ${d.alias ?? d.id}`}
          title="Supprimer"
          onClick={() => {
            if (window.confirm("Supprimer ce dataset ?")) onDelete(d.id);
          }}
          style={{ background: "transparent", border: 0, cursor: "pointer", fontSize: 14 }}
        >
          🗑
        </button>
      </div>
      {error ? (
        <div style={{ color: "red", fontSize: 12, marginLeft: 28 }}>{error}</div>
      ) : null}
      <ParentLineage parentIds={d.parent_ids} datasets={datasets} />
    </li>
  );
}

export function DatasetPanel({
  datasets,
  activeLayers,
  onToggle,
  onDraw,
  drawingActive,
  onClearAll,
  onDelete,
  onRename,
}: Props) {
  const grouped = groupDatasets(datasets);

  return (
    <div
      style={{
        position: "absolute",
        bottom: 0,
        left: 0,
        right: "30%",
        background: "rgba(255,255,255,0.95)",
        borderTop: "1px solid #ddd",
        padding: 12,
        maxHeight: 240,
        overflow: "auto",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <strong>Datasets ({datasets.length})</strong>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={onDraw} disabled={drawingActive}>
            {drawingActive ? "Dessine sur la carte…" : "Dessiner zone"}
          </button>
          <button
            onClick={() => {
              if (window.confirm("Effacer tous les datasets ? La conversation continue.")) {
                onClearAll();
              }
            }}
            disabled={datasets.length === 0}
            aria-label="Tout effacer"
            title="Effacer tous les datasets"
          >
            🗑 Tout effacer
          </button>
        </div>
      </div>
      {datasets.length === 0 && <em>Aucun dataset. Dessine une zone et demande à l&apos;agent.</em>}
      {GROUP_ORDER.map((g) =>
        grouped[g].length === 0 ? null : (
          <section key={g} style={{ marginBottom: 8 }}>
            <h4 style={{ fontSize: 12, color: "#444", margin: "8px 0 4px" }}>
              {GROUP_TITLES[g]} ({grouped[g].length})
            </h4>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {grouped[g].map((d) => (
                <DatasetRow
                  key={d.id}
                  d={d}
                  visible={activeLayers.includes(d.id)}
                  datasets={datasets}
                  onToggle={onToggle}
                  onDelete={onDelete}
                  onRename={onRename}
                />
              ))}
            </ul>
          </section>
        )
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```
cd frontend
npx tsc --noEmit
```

Expected: no errors. (The `GeoPage` callbacks from Task 11 now type-match.)

- [ ] **Step 3: Smoke-test the dev server**

In one terminal: `cd backend && uv run uvicorn geo_agent.main:app --reload`
In another: `cd frontend && npm run dev`

Open `http://localhost:3000`. Verify:

1. The panel renders with three section headers when datasets exist in multiple groups.
2. The trash icon next to a row removes it after the confirm.
3. The pencil opens an inline input; Enter submits; the alias changes.
4. The header "🗑 Tout effacer" empties the panel after the confirm.
5. The chat-header "↻ Nouveau" reloads the page on a clean store.

Document any defects before the commit; the next step assumes the smoke test passes.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/DatasetPanel.tsx
git commit -m "feat(DatasetPanel): grouped rows with icons, per-row actions, lineage"
```

---

## Task 13: `DatasetPanel.test.tsx`

**Files:**
- Create: `frontend/tests/unit/DatasetPanel.test.tsx`

- [ ] **Step 1: Write the test file**

Create `frontend/tests/unit/DatasetPanel.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DatasetPanel } from "@/components/DatasetPanel";
import { DatasetMetaLite } from "@/lib/types";

const ZONE: DatasetMetaLite = {
  id: "result_001",
  alias: "zone_1",
  feature_count: 1,
  bbox: [0, 0, 1, 1],
  layer: null,
  operation: "user_drawing",
  parent_ids: [],
};

const WFS: DatasetMetaLite = {
  id: "result_002",
  alias: null,
  feature_count: 87,
  bbox: [0, 0, 1, 1],
  layer: "pyrr:chaussee",
  operation: "select_features",
  parent_ids: [],
};

const DERIVED: DatasetMetaLite = {
  id: "result_003",
  alias: "filtre_long",
  feature_count: 12,
  bbox: [0, 0, 1, 1],
  layer: null,
  operation: "filter_attributes",
  parent_ids: ["result_002"],
};

const ORPHAN_DERIVED: DatasetMetaLite = {
  id: "result_004",
  alias: null,
  feature_count: 3,
  bbox: [0, 0, 1, 1],
  layer: null,
  operation: "spatial_overlay",
  parent_ids: ["result_999"],
};

interface RenderOptions {
  datasets?: DatasetMetaLite[];
  onDelete?: (id: string) => void;
  onRename?: (id: string, alias: string) => Promise<string | null>;
  onClearAll?: () => void;
  activeLayers?: string[];
}

function renderPanel(opts: RenderOptions = {}) {
  const onToggle = vi.fn();
  const onDraw = vi.fn();
  const onDelete = opts.onDelete ?? vi.fn();
  const onRename = opts.onRename ?? vi.fn(async () => null);
  const onClearAll = opts.onClearAll ?? vi.fn();

  render(
    <DatasetPanel
      datasets={opts.datasets ?? [ZONE, WFS, DERIVED]}
      activeLayers={opts.activeLayers ?? []}
      onToggle={onToggle}
      onDraw={onDraw}
      drawingActive={false}
      onClearAll={onClearAll}
      onDelete={onDelete}
      onRename={onRename}
    />
  );
  return { onToggle, onDraw, onDelete, onRename, onClearAll };
}

describe("DatasetPanel", () => {
  beforeEach(() => {
    vi.stubGlobal("confirm", vi.fn(() => true));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders one section per occupied group", () => {
    renderPanel();
    expect(screen.getByText("Zones dessinées (1)")).toBeInTheDocument();
    expect(screen.getByText("Résultats WFS (1)")).toBeInTheDocument();
    expect(screen.getByText("Dérivés (1)")).toBeInTheDocument();
  });

  it("hides empty groups", () => {
    renderPanel({ datasets: [ZONE] });
    expect(screen.getByText("Zones dessinées (1)")).toBeInTheDocument();
    expect(screen.queryByText(/Résultats WFS/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Dérivés/)).not.toBeInTheDocument();
  });

  it("shows the parent's alias under a derived row", () => {
    renderPanel();
    expect(screen.getByText("result_002")).toBeInTheDocument();
  });

  it("shows a struck-through bare id when the parent is orphaned", () => {
    renderPanel({ datasets: [ORPHAN_DERIVED] });
    const orphan = screen.getByText("result_999");
    expect(orphan).toHaveStyle({ textDecoration: "line-through" });
  });

  it("invokes onDelete after a confirmed click", () => {
    const onDelete = vi.fn();
    renderPanel({ onDelete });
    fireEvent.click(screen.getByLabelText("supprimer zone_1"));
    expect(window.confirm).toHaveBeenCalled();
    expect(onDelete).toHaveBeenCalledWith("result_001");
  });

  it("skips onDelete when the confirm is dismissed", () => {
    (window.confirm as ReturnType<typeof vi.fn>).mockReturnValueOnce(false);
    const onDelete = vi.fn();
    renderPanel({ onDelete });
    fireEvent.click(screen.getByLabelText("supprimer zone_1"));
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("renames a row via inline input and Enter", async () => {
    const onRename = vi.fn(async () => null);
    renderPanel({ onRename });
    fireEvent.click(screen.getByLabelText("renommer zone_1"));
    const input = screen.getByLabelText("nouvel alias") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "centre_ville" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => {
      expect(onRename).toHaveBeenCalledWith("result_001", "centre_ville");
    });
  });

  it("rejects an invalid alias client-side without calling onRename", () => {
    const onRename = vi.fn(async () => null);
    renderPanel({ onRename });
    fireEvent.click(screen.getByLabelText("renommer zone_1"));
    const input = screen.getByLabelText("nouvel alias") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "bad name" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onRename).not.toHaveBeenCalled();
    expect(screen.getByText(/non vide/)).toBeInTheDocument();
  });

  it("surfaces a backend error inline", async () => {
    const onRename = vi.fn(async () => "alias already used");
    renderPanel({ onRename });
    fireEvent.click(screen.getByLabelText("renommer zone_1"));
    const input = screen.getByLabelText("nouvel alias") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "park" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => {
      expect(screen.getByText("alias already used")).toBeInTheDocument();
    });
  });

  it("invokes onClearAll after the confirm", () => {
    const onClearAll = vi.fn();
    renderPanel({ onClearAll });
    fireEvent.click(screen.getByLabelText("Tout effacer"));
    expect(onClearAll).toHaveBeenCalled();
  });

  it("skips onClearAll when the confirm is dismissed", () => {
    (window.confirm as ReturnType<typeof vi.fn>).mockReturnValueOnce(false);
    const onClearAll = vi.fn();
    renderPanel({ onClearAll });
    fireEvent.click(screen.getByLabelText("Tout effacer"));
    expect(onClearAll).not.toHaveBeenCalled();
  });

  it("disables Tout effacer when there are no datasets", () => {
    renderPanel({ datasets: [] });
    expect(screen.getByLabelText("Tout effacer")).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run the tests, expect pass**

```
cd frontend
npm test -- DatasetPanel
```

Expected: 12 tests pass.

- [ ] **Step 3: Run the full frontend test suite**

```
cd frontend
npm test
```

Expected: every test passes (no regressions in the other widgets — adding `parent_ids` is backward-compatible because the zod schema has `.default([])`).

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/unit/DatasetPanel.test.tsx
git commit -m "test(DatasetPanel): cover grouping, lineage, delete, inline rename"
```

---

## Final verification

- [ ] **Step 1: Backend test suite**

```
cd backend
uv run pytest -q
```

Expected: all pass.

- [ ] **Step 2: Frontend test suite**

```
cd frontend
npm test
```

Expected: all pass.

- [ ] **Step 3: Manual smoke test**

Start both services and open `http://localhost:3000`. Walk through the full flow:

1. Draw a zone (`zone_1` appears in **Zones dessinées**).
2. Ask the agent: *"Trouve les chaussées dans cette zone"* (a WFS dataset appears in **Résultats WFS**).
3. Ask: *"Garde celles de plus de 200 m"* (a derived dataset appears in **Dérivés** with `← zone_1` lineage, or whichever id was the parent).
4. Click the pencil on the derived row, rename it, press Enter. The alias updates.
5. Click the trash on the WFS row, confirm. The row disappears and the derived row's lineage now shows the parent id with strikethrough.
6. Click "🗑 Tout effacer" in the panel header, confirm. The panel empties; the chat keeps the conversation history.
7. Click "↻ Nouveau" in the chat header, confirm. The page reloads on an empty store.

- [ ] **Step 4: Commit-history sanity check**

```
git log --oneline -- backend/ frontend/ docs/superpowers/specs/2026-05-11-dataset-management-design.md
```

Expected: one commit per task above, ordered.
