# Geo-agent UI Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the silent / stuck "Chargement…" widget pattern with a unified tool-activity feed (now-playing pill + collapsible log) backed by a new `tool_events` state channel, stop the chat prose from duplicating widget data, and make dataset cards appear as each tool completes.

**Architecture:** Backend adds a `tool_events` channel to `AgentState` (id-keyed reducer, capped at 50), populated by an `@instrumented_tool` decorator that wraps `langchain_core.tools.tool` and amends each tool's `Command.update`. Frontend mounts a `ToolPill` + `ToolActivityLog` driven by that channel and replaces the three per-tool `useCopilotAction` render hooks with a single generic hook that pulls dataset cards from `state.datasets` keyed by `tool_call_id`. `MetadataWidget` loses its `Chargement…` loading state.

**Tech Stack:** Backend — Python 3.12, LangChain/LangGraph, FastAPI, pytest, uv. Frontend — Next.js 16, React 19, CopilotKit, Vitest + Playwright, npm.

**Spec:** `docs/superpowers/specs/2026-05-13-geoagent-ui-feedback-design.md`

---

## File Structure

### New files

```
backend/
  geo_agent/agent/tools/_instrumentation.py            # @instrumented_tool decorator + summarizers
  tests/unit/test_instrumentation.py                   # decorator unit tests
  tests/unit/test_tool_events_reducer.py               # reducer unit tests
  tests/integration/test_graph_tool_events.py          # graph emits tool_events end-to-end

frontend/
  components/ToolActivity/ToolPill.tsx                 # now-playing pill
  components/ToolActivity/ToolActivityLog.tsx          # collapsible log (B contextual + per-row C forensic)
  components/ToolActivity/humanise.ts                  # tool name → human label
  tests/unit/ToolPill.test.tsx
  tests/unit/ToolActivityLog.test.tsx
  tests/e2e/tool-feedback.spec.ts                      # end-to-end regression
```

### Modified files

```
backend/
  geo_agent/models.py                                  # + DatasetMetaLite.tool_call_id
  geo_agent/agent/state.py                             # + tool_events channel + append_tool_events
  geo_agent/agent/error_helpers.py                     # dataset_created_command writes tool_call_id
  geo_agent/agent/tools/wfs/list_layers.py             # decorator import swap
  geo_agent/agent/tools/wfs/describe_layer.py          # decorator import swap
  geo_agent/agent/tools/wfs/select_features.py         # import swap + trim tool_result
  geo_agent/agent/tools/datasets/aggregate.py          # decorator import swap
  geo_agent/agent/tools/datasets/clear_all_datasets.py # decorator import swap
  geo_agent/agent/tools/datasets/delete_dataset.py     # decorator import swap
  geo_agent/agent/tools/datasets/describe_dataset.py   # decorator import swap
  geo_agent/agent/tools/datasets/filter_attributes.py  # decorator import swap
  geo_agent/agent/tools/datasets/rename_dataset.py     # decorator import swap
  geo_agent/agent/tools/datasets/spatial_join.py       # decorator import swap
  geo_agent/agent/tools/datasets/spatial_overlay.py    # decorator import swap
  geo_agent/agent/tools/datasets/transform_geometry.py # decorator import swap
  geo_agent/agent/tools/ui/inspect_dataset.py          # decorator import swap
  geo_agent/agent/tools/ui/show_on_map.py              # decorator import swap (both show_on_map and hide_on_map)
  geo_agent/agent/prompts.py                           # + # Communication style
  tests/unit/test_agent_state.py                       # extend with append_tool_events cases
  tests/unit/test_error_helpers.py                     # tool_call_id propagation case
  tests/unit/test_tool_select_features.py              # assert trimmed tool_result

frontend/
  lib/types.ts                                         # + ToolEvent schema; + DatasetMetaLite.tool_call_id
  components/Widgets/MetadataWidget.tsx                # drop "Chargement…" loading state
  components/GeoPage.tsx                               # 3 render hooks → 1 generic; mount ToolActivity; error chip
  tests/unit/MetadataWidget.test.tsx                   # update tests after props change

frontend/components/AgentStateRenderers/AnalysisProgress.tsx  # DELETE
```

---

## Task 1: Add `tool_call_id` to `DatasetMetaLite` and propagate via `dataset_created_command`

**Files:**
- Modify: `backend/geo_agent/models.py:33-42`
- Modify: `backend/geo_agent/agent/error_helpers.py:68-88`
- Test: `backend/tests/unit/test_error_helpers.py`

This is the foundation that lets the frontend correlate a dataset card with the tool call that produced it.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_error_helpers.py`:

```python
from geo_agent.agent.error_helpers import dataset_created_command
from geo_agent.models import DatasetMetaLite


def test_dataset_created_command_writes_tool_call_id_on_dataset() -> None:
    meta = DatasetMetaLite(
        id="result_007",
        alias="parcs",
        feature_count=12,
        bbox=(0.0, 0.0, 1.0, 1.0),
        layer="parcs",
        operation="select_features",
        parent_ids=[],
    )
    cmd = dataset_created_command(
        meta,
        tool_result={"dataset_id": "result_007"},
        state={"datasets": []},
        tool_call_id="tc-abc123",
    )
    ds = cmd.update["datasets"][0]
    assert ds["tool_call_id"] == "tc-abc123"
    assert ds["id"] == "result_007"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/unit/test_error_helpers.py::test_dataset_created_command_writes_tool_call_id_on_dataset -v
```

Expected: FAIL — KeyError on `tool_call_id` (the field doesn't exist on `DatasetMetaLite` yet).

- [ ] **Step 3: Add the field to `DatasetMetaLite`**

In `backend/geo_agent/models.py`, replace the `DatasetMetaLite` class body:

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
    # tool_call_id is set by dataset_created_command so the frontend can
    # match a dataset card to its originating tool call. It is None for
    # datasets loaded via REST (no tool call) or rehydrated from disk.
    tool_call_id: str | None = None
```

- [ ] **Step 4: Plumb `tool_call_id` through `dataset_created_command`**

In `backend/geo_agent/agent/error_helpers.py`, replace `dataset_created_command`:

```python
def dataset_created_command(
    meta: DatasetMetaLite,
    tool_result: dict[str, Any],
    state: dict[str, Any],
    tool_call_id: str,
) -> Command:
    """Register a newly produced dataset in state.datasets and feed result back to the LLM."""
    current = list(state.get("datasets") or [])
    if not any(d.get("id") == meta.id for d in current):
        ds = meta.model_dump(mode="json")
        ds["tool_call_id"] = tool_call_id
        current.append(ds)
    return Command(
        update={
            "datasets": current,
            "messages": [
                ToolMessage(
                    content=json.dumps(tool_result),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/unit/test_error_helpers.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Sanity check — full backend tests still pass**

```bash
cd backend && uv run pytest
```

Expected: green. `DatasetMetaLite` consumers don't care about the new optional field.

- [ ] **Step 7: Commit**

```bash
git add backend/geo_agent/models.py backend/geo_agent/agent/error_helpers.py backend/tests/unit/test_error_helpers.py
git commit -m "feat(state): tag DatasetMetaLite with tool_call_id from dataset_created_command"
```

---

## Task 2: Add `tool_events` channel + `append_tool_events` reducer

**Files:**
- Modify: `backend/geo_agent/agent/state.py`
- Test: `backend/tests/unit/test_agent_state.py`

The channel is id-keyed so a `running` event and its `ok`/`error` final state collapse to one entry. Cap at 50 distinct events.

- [ ] **Step 1: Write failing reducer tests**

Append to `backend/tests/unit/test_agent_state.py`:

```python
from geo_agent.agent.state import TOOL_EVENTS_CAP, append_tool_events


def _ev(eid: str, status: str = "running", **kw) -> dict:
    return {"id": eid, "status": status, **kw}


def test_append_tool_events_appends_distinct() -> None:
    out = append_tool_events([_ev("te_1")], [_ev("te_2")])
    assert [e["id"] for e in out] == ["te_1", "te_2"]


def test_append_tool_events_overwrites_same_id() -> None:
    # start (running) → end (ok) on the same id collapses to a single entry
    out = append_tool_events(
        [_ev("te_1", "running", tool="select_features")],
        [_ev("te_1", "ok", tool="select_features", duration_ms=1200)],
    )
    assert len(out) == 1
    assert out[0]["status"] == "ok"
    assert out[0]["duration_ms"] == 1200


def test_append_tool_events_preserves_chronological_order_on_overwrite() -> None:
    # te_1 started first, te_2 second; when te_1 finishes it should keep its position
    state = append_tool_events([], [_ev("te_1", "running")])
    state = append_tool_events(state, [_ev("te_2", "running")])
    state = append_tool_events(state, [_ev("te_1", "ok")])
    assert [e["id"] for e in state] == ["te_1", "te_2"]
    assert state[0]["status"] == "ok"


def test_append_tool_events_caps_distinct_ids() -> None:
    left = [_ev(f"te_{i}") for i in range(TOOL_EVENTS_CAP)]
    right = [_ev("te_new")]
    out = append_tool_events(left, right)
    assert len(out) == TOOL_EVENTS_CAP
    assert out[-1]["id"] == "te_new"
    assert out[0]["id"] == "te_1"  # te_0 dropped


def test_append_tool_events_handles_none() -> None:
    assert append_tool_events(None, [_ev("te_1")]) == [_ev("te_1")]  # type: ignore[arg-type]
    assert append_tool_events([_ev("te_1")], None) == [_ev("te_1")]  # type: ignore[arg-type]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/unit/test_agent_state.py -v
```

Expected: ImportError on `TOOL_EVENTS_CAP` / `append_tool_events`.

- [ ] **Step 3: Add reducer and channel**

In `backend/geo_agent/agent/state.py`, add after the existing constants/reducers and before `class AgentState`:

```python
TOOL_EVENTS_CAP = 50


def append_tool_events(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Append tool lifecycle events keyed by `id`. A second write for the same
    id (running → ok/error) overwrites the first while preserving its position.
    Total distinct events are capped at TOOL_EVENTS_CAP, oldest dropped first."""
    left = left or []
    if right is None:
        return left
    # OrderedDict preserves insertion order on update — important so a finishing
    # event doesn't reorder ahead of newer running events.
    merged: dict[str, dict[str, Any]] = {}
    for e in left:
        merged[e["id"]] = e
    for e in right:
        if e["id"] in merged:
            merged[e["id"]] = e
        else:
            merged[e["id"]] = e  # appends to end
    items = list(merged.values())
    return items[-TOOL_EVENTS_CAP:]
```

Then extend `AgentState` and `build_initial_state`:

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    remaining_steps: RemainingSteps
    datasets: Annotated[list[dict[str, Any]], merge_datasets]
    active_layers: Annotated[list[str], merge_active_layers]
    errors: Annotated[list[dict[str, Any]], append_errors]
    inspections: Annotated[list[dict[str, Any]], append_inspections]
    tool_events: Annotated[list[dict[str, Any]], append_tool_events]


def build_initial_state() -> AgentState:
    return {
        "messages": [],
        "datasets": [],
        "active_layers": [],
        "errors": [],
        "inspections": [],
        "tool_events": [],
    }  # type: ignore[typeddict-item]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/unit/test_agent_state.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/agent/state.py backend/tests/unit/test_agent_state.py
git commit -m "feat(state): tool_events channel keyed by id, capped at 50"
```

---

## Task 3: Build `instrumented_tool` decorator with summarizers

**Files:**
- Create: `backend/geo_agent/agent/tools/_instrumentation.py`
- Test: `backend/tests/unit/test_instrumentation.py`

The decorator wraps `langchain_core.tools.tool`. Tools either return a `Command` (current pattern in this codebase) — the decorator amends `update["tool_events"]` with the final event. Or they return a scalar/dict — the decorator wraps it in an equivalent `Command`.

- [ ] **Step 1: Write the unit tests (file does not exist yet)**

Create `backend/tests/unit/test_instrumentation.py`:

```python
import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from geo_agent.agent.tools._instrumentation import (
    _build_event,
    _summarize_args,
    instrumented_tool,
)


@instrumented_tool
def _echo(value: str, tool_call_id: str) -> Command:
    """Test tool: return a Command echoing the value."""
    return Command(
        update={
            "messages": [ToolMessage(content=f"echo:{value}", tool_call_id=tool_call_id)],
        }
    )


@instrumented_tool
def _scalar(value: str, tool_call_id: str) -> str:
    """Test tool: return a scalar (LangChain auto-wraps it)."""
    return f"scalar:{value}"


@instrumented_tool
def _raiser(tool_call_id: str) -> Command:
    raise RuntimeError("kaboom")


@instrumented_tool
def _tool_errored(tool_call_id: str) -> Command:
    """Test tool: return a Command with a structured error (mimics tool_error_command)."""
    return Command(
        update={
            "errors": [{"code": "bad_input", "message": "nope"}],
            "messages": [ToolMessage(content='{"error":"nope"}', tool_call_id=tool_call_id)],
        }
    )


def test_event_payload_shape() -> None:
    ev = _build_event(
        event_id="te_x",
        tool_call_id="tc_1",
        tool="select_features",
        args_raw={"layer": "chaussees"},
        status="running",
        started_at=1.0,
    )
    assert ev["id"] == "te_x"
    assert ev["tool"] == "select_features"
    assert ev["status"] == "running"
    assert ev["started_at"] == 1.0
    assert ev["ended_at"] is None
    assert ev["duration_ms"] is None
    assert "args_summary" in ev
    assert "args_raw" in ev


def test_summarize_args_redacts_injected() -> None:
    out = _summarize_args({"layer": "x", "tool_call_id": "tc_1", "state": {}})
    assert "tool_call_id" not in out
    assert "state" not in out
    assert out["layer"] == "x"


def test_command_returning_tool_gets_tool_events_appended() -> None:
    result = _echo.invoke({"name": "_echo", "args": {"value": "hi"}, "id": "tc_1", "type": "tool_call"})
    assert isinstance(result, Command)
    events = result.update["tool_events"]
    assert len(events) == 1
    final = events[0]
    assert final["status"] == "ok"
    assert final["tool"] == "_echo"
    assert final["tool_call_id"] == "tc_1"
    assert final["duration_ms"] is not None
    # The original update["messages"] is preserved
    assert any(isinstance(m, ToolMessage) for m in result.update["messages"])


def test_scalar_returning_tool_gets_wrapped_in_command() -> None:
    result = _scalar.invoke({"name": "_scalar", "args": {"value": "hi"}, "id": "tc_2", "type": "tool_call"})
    assert isinstance(result, Command)
    events = result.update["tool_events"]
    assert events[0]["status"] == "ok"
    # ToolMessage was synthesised with the scalar content
    msgs = result.update["messages"]
    assert msgs and isinstance(msgs[0], ToolMessage)
    assert msgs[0].content == "scalar:hi"


def test_exception_writes_error_event_and_reraises() -> None:
    with pytest.raises(RuntimeError, match="kaboom"):
        _raiser.invoke({"name": "_raiser", "args": {}, "id": "tc_3", "type": "tool_call"})


def test_tool_error_command_results_in_error_event_not_ok() -> None:
    result = _tool_errored.invoke({"name": "_tool_errored", "args": {}, "id": "tc_4", "type": "tool_call"})
    assert isinstance(result, Command)
    events = result.update["tool_events"]
    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["error"]["code"] == "bad_input"
    # Pre-existing errors stay intact (the decorator amends tool_events without touching errors)
    assert result.update["errors"][0]["code"] == "bad_input"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/unit/test_instrumentation.py -v
```

Expected: ImportError on the module.

- [ ] **Step 3: Create the decorator module**

Create `backend/geo_agent/agent/tools/_instrumentation.py`:

```python
"""@instrumented_tool — wraps langchain_core.tools.tool to emit tool_events.

Replaces `from langchain_core.tools import tool`. Adds a `tool_events` entry
to the returned Command's update (running emitted via langgraph stream writer
when available; final event always written via Command).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool as langchain_tool
from langgraph.types import Command

# A summarizer takes (args_raw, result) and returns (args_summary, result_summary).
Summarizer = Callable[[dict[str, Any], Any], tuple[str, str]]


def _summarize_args(args: dict[str, Any]) -> dict[str, Any]:
    """Strip injected runtime args so the forensic view shows only what a human typed."""
    return {k: v for k, v in args.items() if k not in {"tool_call_id", "state"}}


def _summarize_default(args_raw: dict[str, Any], result: Any) -> tuple[str, str]:
    args_summary = ", ".join(f"{k}={v!r}" for k, v in args_raw.items())[:200]
    if isinstance(result, Command):
        # We can't peek at the model's view of the result without unwrapping the ToolMessage.
        result_summary = "ok"
    else:
        result_summary = repr(result)[:200]
    return args_summary, result_summary


SUMMARIZERS: dict[str, Summarizer] = {}


def _summarize_select_features(args: dict[str, Any], result: Any) -> tuple[str, str]:
    layer = args.get("layer", "?")
    pred = args.get("spatial_predicate") or "whole-layer"
    alias = args.get("alias")
    parts = [f"layer={layer}", f"predicate={pred}"]
    if alias:
        parts.append(f"alias={alias}")
    args_summary = ", ".join(parts)
    result_summary = _peek_dataset_result(result)
    return args_summary, result_summary


def _summarize_filter_attributes(args: dict[str, Any], result: Any) -> tuple[str, str]:
    pred = args.get("predicate") or {}
    if hasattr(pred, "model_dump"):
        pred = pred.model_dump()
    args_summary = f"on={args.get('dataset_id')} {pred.get('property')} {pred.get('op')} {pred.get('value')!r}"
    return args_summary, _peek_dataset_result(result)


def _summarize_describe_wfs_layer(args: dict[str, Any], result: Any) -> tuple[str, str]:
    return f"layer={args.get('layer')}", "schema returned"


def _peek_dataset_result(result: Any) -> str:
    """Pull the new dataset id + feature_count out of a Command's ToolMessage, if present."""
    if not isinstance(result, Command):
        return repr(result)[:200]
    for m in result.update.get("messages", []) or []:
        if isinstance(m, ToolMessage):
            import json
            try:
                payload = json.loads(m.content) if isinstance(m.content, str) else {}
            except json.JSONDecodeError:
                return str(m.content)[:200]
            ds_id = payload.get("dataset_id")
            fc = payload.get("feature_count")
            if ds_id is not None:
                return f"{fc} features → {ds_id}"
            return str(payload)[:200]
    return "ok"


SUMMARIZERS["select_features"] = _summarize_select_features
SUMMARIZERS["filter_attributes"] = _summarize_filter_attributes
SUMMARIZERS["describe_wfs_layer"] = _summarize_describe_wfs_layer
# Spatial/derived tools share the dataset-result shape — reuse the peek.
for _name in ("spatial_overlay", "spatial_join", "transform_geometry"):
    SUMMARIZERS[_name] = lambda a, r, name=_name: (
        ", ".join(f"{k}={v!r}" for k, v in _summarize_args(a).items())[:200],
        _peek_dataset_result(r),
    )


def _build_event(
    *,
    event_id: str,
    tool_call_id: str,
    tool: str,
    args_raw: dict[str, Any],
    status: str,
    started_at: float,
    ended_at: float | None = None,
    result_summary: str | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args_summary = ""
    sumr = SUMMARIZERS.get(tool)
    if sumr is not None and result_summary is None:
        # only resolve once we have the result; for the running event we use a default summary
        args_summary = ", ".join(f"{k}={v!r}" for k, v in args_raw.items())[:200]
    else:
        args_summary = ", ".join(f"{k}={v!r}" for k, v in args_raw.items())[:200]
    ev: dict[str, Any] = {
        "id": event_id,
        "tool_call_id": tool_call_id,
        "tool": tool,
        "args_summary": args_summary,
        "args_raw": args_raw,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": int((ended_at - started_at) * 1000) if ended_at is not None else None,
        "status": status,
    }
    if result_summary is not None:
        ev["result_summary"] = result_summary
    if error is not None:
        ev["error"] = error
    return ev


def _emit_running(event: dict[str, Any]) -> None:
    """Best-effort interim write so the frontend pill can show before the tool returns."""
    try:
        from langgraph.config import get_stream_writer  # imported lazily

        writer = get_stream_writer()
    except Exception:
        return
    try:
        writer({"tool_events": [event]})
    except Exception:
        # Non-streaming context or writer not configured for this run.
        return


def _attach_event_to_command(cmd: Command, event: dict[str, Any]) -> Command:
    update = dict(cmd.update or {})
    update["tool_events"] = [*update.get("tool_events", []), event]
    return Command(update=update, goto=getattr(cmd, "goto", None))


def instrumented_tool(*args, **kwargs):
    """Drop-in replacement for `langchain_core.tools.tool`.

    Usage (identical to LangChain):

        @instrumented_tool
        async def my_tool(...): ...

        @instrumented_tool("custom_name", description="...")
        async def my_tool(...): ...
    """
    # Support both @instrumented_tool and @instrumented_tool(...) forms
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return _wrap(args[0], langchain_tool(args[0]))

    def deco(fn: Callable):
        return _wrap(fn, langchain_tool(*args, **kwargs)(fn))

    return deco


def _wrap(fn: Callable, base_tool):
    """Return a Tool whose invoke/ainvoke wrap the original with tool_events bookkeeping."""
    tool_name = base_tool.name
    orig_invoke = base_tool.invoke
    orig_ainvoke = base_tool.ainvoke

    def _make_event(tool_call_id: str, args_raw: dict[str, Any]) -> tuple[str, float]:
        eid = "te_" + uuid.uuid4().hex[:12]
        started_at = time.time()
        return eid, started_at

    def _finalize(
        result: Any,
        eid: str,
        tool_call_id: str,
        tool_args: dict[str, Any],
        started_at: float,
    ) -> Command:
        ended_at = time.time()
        sumr = SUMMARIZERS.get(tool_name, _summarize_default)
        args_summary, result_summary = sumr(tool_args, result)
        # A tool that returned via `tool_error_command(...)` produces a Command whose
        # update["errors"] is non-empty — surface that as a tool_events error rather
        # than a misleading "ok".
        is_tool_error = isinstance(result, Command) and bool(result.update.get("errors"))
        if is_tool_error:
            err = result.update["errors"][-1]
            final = _build_event(
                event_id=eid,
                tool_call_id=tool_call_id,
                tool=tool_name,
                args_raw=tool_args,
                status="error",
                started_at=started_at,
                ended_at=ended_at,
                error={"code": err.get("code", "unknown"), "message": err.get("message", "")},
            )
            final["args_summary"] = args_summary
            return _attach_event_to_command(result, final)
        final = _build_event(
            event_id=eid,
            tool_call_id=tool_call_id,
            tool=tool_name,
            args_raw=tool_args,
            status="ok",
            started_at=started_at,
            ended_at=ended_at,
            result_summary=result_summary,
        )
        final["args_summary"] = args_summary
        if isinstance(result, Command):
            return _attach_event_to_command(result, final)
        # Wrap a scalar/dict result in an equivalent Command.
        content = result if isinstance(result, str) else _to_json_safe(result)
        return Command(
            update={
                "messages": [ToolMessage(content=content, tool_call_id=tool_call_id)],
                "tool_events": [final],
            }
        )

    def _on_error(
        exc: BaseException,
        eid: str,
        tool_call_id: str,
        tool_args: dict[str, Any],
        started_at: float,
    ) -> dict[str, Any]:
        ended_at = time.time()
        return _build_event(
            event_id=eid,
            tool_call_id=tool_call_id,
            tool=tool_name,
            args_raw=tool_args,
            status="error",
            started_at=started_at,
            ended_at=ended_at,
            result_summary=None,
            error={"code": "internal_error", "message": str(exc)},
        )

    def _extract(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        tool_call_id = call.get("id") or "unknown"
        args_raw = _summarize_args(dict(call.get("args") or {}))
        return tool_call_id, args_raw

    def patched_invoke(call, config=None, **kw):
        tool_call_id, args_raw = _extract(call)
        eid, started_at = _make_event(tool_call_id, args_raw)
        _emit_running(
            _build_event(
                event_id=eid,
                tool_call_id=tool_call_id,
                tool=tool_name,
                args_raw=args_raw,
                status="running",
                started_at=started_at,
            )
        )
        try:
            result = orig_invoke(call, config=config, **kw)
        except BaseException as exc:
            _emit_running(_on_error(exc, eid, tool_call_id, args_raw, started_at))
            raise
        return _finalize(result, eid, tool_call_id, args_raw, started_at)

    async def patched_ainvoke(call, config=None, **kw):
        tool_call_id, args_raw = _extract(call)
        eid, started_at = _make_event(tool_call_id, args_raw)
        _emit_running(
            _build_event(
                event_id=eid,
                tool_call_id=tool_call_id,
                tool=tool_name,
                args_raw=args_raw,
                status="running",
                started_at=started_at,
            )
        )
        try:
            result = await orig_ainvoke(call, config=config, **kw)
        except BaseException as exc:
            _emit_running(_on_error(exc, eid, tool_call_id, args_raw, started_at))
            raise
        return _finalize(result, eid, tool_call_id, args_raw, started_at)

    base_tool.invoke = patched_invoke  # type: ignore[attr-defined]
    base_tool.ainvoke = patched_ainvoke  # type: ignore[attr-defined]
    return base_tool


def _to_json_safe(value: Any) -> str:
    import json

    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/unit/test_instrumentation.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/agent/tools/_instrumentation.py backend/tests/unit/test_instrumentation.py
git commit -m "feat(tools): @instrumented_tool decorator emits tool_events"
```

---

## Task 4: Wire all 15 tools to `instrumented_tool`

**Files modified (import swap only):**
- `backend/geo_agent/agent/tools/wfs/list_layers.py`
- `backend/geo_agent/agent/tools/wfs/describe_layer.py`
- `backend/geo_agent/agent/tools/wfs/select_features.py`
- `backend/geo_agent/agent/tools/datasets/aggregate.py`
- `backend/geo_agent/agent/tools/datasets/clear_all_datasets.py`
- `backend/geo_agent/agent/tools/datasets/delete_dataset.py`
- `backend/geo_agent/agent/tools/datasets/describe_dataset.py`
- `backend/geo_agent/agent/tools/datasets/filter_attributes.py`
- `backend/geo_agent/agent/tools/datasets/rename_dataset.py`
- `backend/geo_agent/agent/tools/datasets/spatial_join.py`
- `backend/geo_agent/agent/tools/datasets/spatial_overlay.py`
- `backend/geo_agent/agent/tools/datasets/transform_geometry.py`
- `backend/geo_agent/agent/tools/ui/inspect_dataset.py`
- `backend/geo_agent/agent/tools/ui/show_on_map.py`
- Test: `backend/tests/integration/test_graph_tool_events.py`

The swap is mechanical: change one line per file.

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/integration/test_graph_tool_events.py`:

```python
"""Integration: invoking a tool through its instrumented wrapper writes a final
tool_events entry into the returned Command. Uses select_features as a witness
for the whole decorator pipeline (which is uniform across all 15 tools)."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from geo_agent.agent.registry import Services
from geo_agent.agent.tools.wfs.select_features import PolygonSource, select_features
from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore
from geo_agent.services.wfs_client import FeatureTypeSchema


@pytest.fixture
def services(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    wfs = AsyncMock()
    wfs.describe_feature_type.return_value = FeatureTypeSchema(
        type_name="montreal:parcs",
        geom_property="geom",
        attribute_schema={"nom": "string"},
    )
    wfs.get_features.return_value = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {"nom": "parc A"}}
        ],
    }
    services = Services(settings=settings, wfs=wfs, store=FileSystemResultStore(data_dir=data_dir))
    monkeypatch.setattr("geo_agent.agent.tools.wfs.select_features.get_services", lambda: services)
    return services


async def test_select_features_emits_final_tool_event(services: Services) -> None:
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    call = {
        "name": "select_features",
        "args": {
            "layer": "montreal:parcs",
            "geometry_source": PolygonSource(type="polygon", polygon=polygon).model_dump(),
            "spatial_predicate": "within",
            "alias": "parcs_test",
        },
        "id": "tc_abc",
        "type": "tool_call",
    }
    cmd = await select_features.ainvoke(call)
    events = cmd.update["tool_events"]
    assert len(events) == 1
    ev = events[0]
    assert ev["status"] == "ok"
    assert ev["tool"] == "select_features"
    assert ev["tool_call_id"] == "tc_abc"
    assert ev["duration_ms"] is not None and ev["duration_ms"] >= 0
    assert ev["args_summary"].startswith("layer=montreal:parcs")
    assert "1 features → " in ev["result_summary"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/integration/test_graph_tool_events.py -v
```

Expected: KeyError or AssertionError on `tool_events` (the tool still uses the unwrapped `@tool`).

- [ ] **Step 3: Swap the import in every tool file**

In each of the 14 tool files listed above, change the import line:

```python
# Before
from langchain_core.tools import InjectedToolCallId, tool
# After
from langchain_core.tools import InjectedToolCallId
from geo_agent.agent.tools._instrumentation import instrumented_tool as tool
```

The `@tool` decorator lines below stay unchanged. Files that only import `tool` (without `InjectedToolCallId`) need only:

```python
# Before
from langchain_core.tools import tool
# After
from geo_agent.agent.tools._instrumentation import instrumented_tool as tool
```

To find which files need which form:

```bash
cd backend && grep -l "from langchain_core.tools import.*tool" geo_agent/agent/tools/
```

- [ ] **Step 4: Run the integration test**

```bash
cd backend && uv run pytest tests/integration/test_graph_tool_events.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the full backend test suite to catch regressions**

```bash
cd backend && uv run pytest
```

Expected: all green. Existing tool tests that pop datasets from `cmd.update["datasets"]` continue to work because the decorator only appends `tool_events` and leaves other update keys intact.

- [ ] **Step 6: Commit**

```bash
git add backend/geo_agent/agent/tools/ backend/tests/integration/test_graph_tool_events.py
git commit -m "feat(tools): wire 15 tools through @instrumented_tool"
```

---

## Task 5: Trim `select_features` tool_result payload

**Files:**
- Modify: `backend/geo_agent/agent/tools/wfs/select_features.py:278-289`
- Test: `backend/tests/unit/test_tool_select_features.py`

The other dataset-creating tools (`filter_attributes`, `spatial_overlay`, `spatial_join`, `transform_geometry`) already return only `{dataset_id, alias, feature_count, bbox}`. Only `select_features` still ships `attribute_schema` in its tool_result. We also drop `bbox` here for consistency — the model has it in the per-turn dataset summary in the system prompt.

- [ ] **Step 1: Add the failing assertion**

In `backend/tests/unit/test_tool_select_features.py`, modify the first test `test_select_features_with_polygon` to assert the trimmed shape. Add this assertion block at the end of the function:

```python
    # The ToolMessage payload sent back to the model is intentionally minimal —
    # bbox and attribute_schema are visible to the user via the DATASET widget
    # and re-fetchable by the model via describe_dataset if needed.
    import json
    tm = result.update["messages"][0]
    payload = json.loads(tm.content)
    assert set(payload.keys()) == {"dataset_id", "alias", "feature_count"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/unit/test_tool_select_features.py::test_select_features_with_polygon -v
```

Expected: AssertionError on the set comparison (the payload still has `bbox` and `attribute_schema`).

- [ ] **Step 3: Trim the payload**

In `backend/geo_agent/agent/tools/wfs/select_features.py`, replace the final `dataset_created_command` block (lines ~278-289):

```python
    return dataset_created_command(
        meta_lite,
        tool_result={
            "dataset_id": rid,
            "alias": meta.alias,
            "feature_count": meta.feature_count,
        },
        state=state,
        tool_call_id=tool_call_id,
    )
```

For the other dataset-creating tools (`filter_attributes`, `spatial_overlay`, `spatial_join`, `transform_geometry`), also drop `bbox` from their `tool_result`. In each of those four files, find the final `dataset_created_command(...)` call and delete the `"bbox": list(meta.bbox),` line from the `tool_result={...}` block. After the change, each block reads:

```python
    return dataset_created_command(
        meta_lite,   # or _meta_lite(meta) — depending on the file's helper
        tool_result={
            "dataset_id": rid,    # or new_id — keep what the file already uses
            "alias": meta.alias,
            "feature_count": meta.feature_count,
        },
        state=state,
        tool_call_id=tool_call_id,
    )
```

Locate the exact lines with:

```bash
cd backend && grep -n "list(meta.bbox)" geo_agent/agent/tools/datasets/filter_attributes.py geo_agent/agent/tools/datasets/spatial_overlay.py geo_agent/agent/tools/datasets/spatial_join.py geo_agent/agent/tools/datasets/transform_geometry.py
```

Delete each matched line. Do not touch `aggregate.py` (it does not produce a dataset).

- [ ] **Step 4: Run all dataset-creating-tool tests**

```bash
cd backend && uv run pytest tests/unit/test_tool_select_features.py tests/unit/test_tool_filter_attributes.py tests/unit/test_tool_spatial_overlay.py tests/unit/test_tool_spatial_join.py tests/unit/test_tool_transform_geometry.py -v
```

Expected: all PASS. If any test asserts on `bbox` in the tool_result message, update it to assert the trimmed shape — the user-facing widget still gets `bbox` via `state.datasets`.

- [ ] **Step 5: Run the full backend test suite**

```bash
cd backend && uv run pytest
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add backend/geo_agent/agent/tools/wfs/select_features.py backend/geo_agent/agent/tools/datasets/filter_attributes.py backend/geo_agent/agent/tools/datasets/spatial_overlay.py backend/geo_agent/agent/tools/datasets/spatial_join.py backend/geo_agent/agent/tools/datasets/transform_geometry.py backend/tests/unit/test_tool_select_features.py
git commit -m "feat(tools): trim dataset tool_result to {dataset_id, alias, feature_count}"
```

---

## Task 6: Add `# Communication style` to the system prompt

**Files:**
- Modify: `backend/geo_agent/agent/prompts.py`
- Test: `backend/tests/unit/test_prompt_builder.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/unit/test_prompt_builder.py`:

```python
def test_system_prompt_has_communication_style_section() -> None:
    from geo_agent.agent.prompts import SYSTEM_PROMPT

    assert "# Communication style" in SYSTEM_PROMPT
    # Concrete anti-duplication guidance present
    assert "do not repeat" in SYSTEM_PROMPT.lower() or "ne répète" in SYSTEM_PROMPT.lower()
    # Specific forbidden things named
    for token in ("feature_count", "bbox", "tool"):
        assert token in SYSTEM_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/unit/test_prompt_builder.py::test_system_prompt_has_communication_style_section -v
```

Expected: AssertionError.

- [ ] **Step 3: Insert the section**

In `backend/geo_agent/agent/prompts.py`, immediately after the `# Role` block (after the line ending with `…spatial/statistical queries.`) and before `# Core rules`, insert:

```
# Communication style

Widgets (DATASET cards, activity pill, activity log, error chips) appear
in the chat alongside your text. They automatically show, for each tool
call: tool name, duration, args, result counts, error codes. For each
dataset they show: id, alias, feature_count, bbox, layer, lineage.

**Do NOT repeat in text anything the widget already shows.** Specifically:
- never restate feature counts, dataset IDs, bbox coordinates, sizes,
  durations, error codes, or attribute schemas in your prose;
- never write "I called tool X" — the activity pill already does that.

**What to write instead:**
- Before a tool call: one short transition phrase that names your next
  step in plain language ("Je récupère les chaussées dans ta zone.",
  "Je filtre par longueur.").
- After all tools for a turn: one short closing line — typically a
  question proposing the next analytical step, or a qualitative
  observation the widgets can't convey (a name, a pattern, a caveat).
- If a step required a non-obvious choice (e.g. buffering then
  dissolving before filtering), say *why* in one sentence — that's the
  part widgets can't show.

**Default to brevity.** If the user asked you to fetch something and
you got it: "Voilà. Tu veux que je l'affiche ?" beats a recap.

```

- [ ] **Step 4: Run prompt-builder tests**

```bash
cd backend && uv run pytest tests/unit/test_prompt_builder.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/agent/prompts.py backend/tests/unit/test_prompt_builder.py
git commit -m "feat(prompt): add # Communication style anti-duplication guidance"
```

---

## Task 7: Update frontend `lib/types.ts` with `ToolEvent` schema + `tool_call_id` on dataset

**Files:**
- Modify: `frontend/lib/types.ts`

- [ ] **Step 1: Add types**

In `frontend/lib/types.ts`, replace the `DatasetMetaLite` and `AgentState` exports and add `ToolEvent`:

```typescript
import { z } from "zod";

export const DatasetMetaLite = z.object({
  id: z.string(),
  alias: z.string().nullable(),
  feature_count: z.number(),
  bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  layer: z.string().nullable(),
  operation: z.string(),
  parent_ids: z.array(z.string()).default([]),
  tool_call_id: z.string().nullable().optional(),
});
export type DatasetMetaLite = z.infer<typeof DatasetMetaLite>;

export const ToolEvent = z.object({
  id: z.string(),
  tool_call_id: z.string(),
  tool: z.string(),
  args_summary: z.string(),
  args_raw: z.record(z.string(), z.unknown()),
  started_at: z.number(),
  ended_at: z.number().nullable(),
  duration_ms: z.number().nullable(),
  status: z.enum(["running", "ok", "error"]),
  result_summary: z.string().optional(),
  error: z
    .object({
      code: z.string(),
      message: z.string(),
    })
    .optional(),
});
export type ToolEvent = z.infer<typeof ToolEvent>;
```

Then extend the existing `AgentState` schema to include `tool_events: z.array(ToolEvent).default([])`:

```typescript
export const AgentState = z.object({
  datasets: z.array(DatasetMetaLite.passthrough()),
  active_layers: z.array(z.string()),
  errors: z.array(ToolError),
  inspections: z.array(InspectResult).optional(),
  tool_events: z.array(ToolEvent).default([]),
});
export type AgentState = z.infer<typeof AgentState>;
```

- [ ] **Step 2: Type-check the frontend**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors. (Existing consumers of `AgentState.tool_events` don't exist yet, so adding the field is safe.)

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts
git commit -m "feat(types): ToolEvent schema; tool_call_id on DatasetMetaLite"
```

---

## Task 8: Build `ToolPill` component

**Files:**
- Create: `frontend/components/ToolActivity/ToolPill.tsx`
- Create: `frontend/components/ToolActivity/humanise.ts`
- Test: `frontend/tests/unit/ToolPill.test.tsx`

The pill renders the latest `tool_events` entry whose `status === "running"`, with 150ms appearance debounce and 100ms disappearance debounce. Stalled state at 60s.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/unit/ToolPill.test.tsx`:

```tsx
import { render, screen, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToolPill } from "@/components/ToolActivity/ToolPill";
import type { ToolEvent } from "@/lib/types";

const baseEv = (overrides: Partial<ToolEvent> = {}): ToolEvent => ({
  id: "te_1",
  tool_call_id: "tc_1",
  tool: "select_features",
  args_summary: "layer=chaussees",
  args_raw: { layer: "chaussees" },
  started_at: Date.now() / 1000,
  ended_at: null,
  duration_ms: null,
  status: "running",
  ...overrides,
});

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ToolPill", () => {
  it("renders nothing when there is no running event", () => {
    const { container } = render(<ToolPill events={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing during the 150ms appearance debounce", () => {
    render(<ToolPill events={[baseEv()]} />);
    expect(screen.queryByText(/Sélection/i)).toBeNull();
    act(() => {
      vi.advanceTimersByTime(149);
    });
    expect(screen.queryByText(/Sélection/i)).toBeNull();
  });

  it("renders after 150ms with the humanised tool name", () => {
    render(<ToolPill events={[baseEv()]} />);
    act(() => {
      vi.advanceTimersByTime(160);
    });
    expect(screen.getByText(/Sélection de features WFS/i)).toBeInTheDocument();
  });

  it("disappears with a 100ms debounce after the event transitions to ok", () => {
    const running = baseEv();
    const { rerender } = render(<ToolPill events={[running]} />);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.getByText(/Sélection/i)).toBeInTheDocument();
    rerender(
      <ToolPill events={[{ ...running, status: "ok", ended_at: Date.now() / 1000, duration_ms: 100 }]} />
    );
    // Still visible immediately after transition
    expect(screen.getByText(/Sélection/i)).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(120);
    });
    expect(screen.queryByText(/Sélection/i)).toBeNull();
  });

  it("shows the stalled message at 60s", () => {
    const long = baseEv({ started_at: (Date.now() - 65_000) / 1000 });
    render(<ToolPill events={[long]} />);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.getByText(/prend plus longtemps/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npm test -- ToolPill
```

Expected: import error.

- [ ] **Step 3: Add humanisation table**

Create `frontend/components/ToolActivity/humanise.ts`:

```typescript
const LABELS: Record<string, string> = {
  list_wfs_layers: "Liste des couches WFS",
  describe_wfs_layer: "Inspection de la couche WFS",
  select_features: "Sélection de features WFS",
  filter_attributes: "Filtrage par attribut",
  aggregate: "Agrégation",
  describe_dataset: "Lecture des métadonnées",
  spatial_overlay: "Overlay spatial",
  spatial_join: "Jointure spatiale",
  transform_geometry: "Transformation géométrique",
  delete_dataset: "Suppression du dataset",
  rename_dataset: "Renommage du dataset",
  clear_all_datasets: "Nettoyage de tous les datasets",
  show_on_map: "Affichage sur la carte",
  hide_on_map: "Masquage de la couche",
  inspect_dataset: "Inspection du dataset",
};

export function humanise(tool: string): string {
  return LABELS[tool] ?? tool;
}
```

- [ ] **Step 4: Build the pill component**

Create `frontend/components/ToolActivity/ToolPill.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import type { ToolEvent } from "@/lib/types";
import { humanise } from "./humanise";

const APPEAR_MS = 150;
const HIDE_MS = 100;
const STALLED_MS = 60_000;

interface Props {
  events: ToolEvent[];
}

export function ToolPill({ events }: Props) {
  const running = [...events].reverse().find((e) => e.status === "running");
  const [visible, setVisible] = useState<ToolEvent | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (running) {
      timerRef.current = setTimeout(() => setVisible(running), APPEAR_MS);
    } else if (visible) {
      timerRef.current = setTimeout(() => setVisible(null), HIDE_MS);
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [running, visible]);

  // Live counter — refresh every 250ms while visible
  useEffect(() => {
    if (!visible) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [visible]);

  if (!visible) return null;
  const elapsedMs = now - visible.started_at * 1000;
  const stalled = elapsedMs > STALLED_MS;
  const seconds = (elapsedMs / 1000).toFixed(1);

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        background: stalled ? "#fbbf24" : "#0ea5e9",
        color: "#fff",
        padding: "6px 12px",
        borderRadius: 999,
        fontFamily: "system-ui",
        fontSize: 12,
        fontWeight: 500,
        boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
      }}
    >
      <span aria-hidden style={{ animation: "spin 1.2s linear infinite" }}>⟳</span>
      <span>{humanise(visible.tool)}</span>
      <span style={{ opacity: 0.85, fontFamily: "monospace" }}>{seconds}s</span>
      {stalled && (
        <span style={{ marginLeft: 4, fontStyle: "italic" }}>
          L'opération prend plus longtemps que prévu
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd frontend && npm test -- ToolPill
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/ToolActivity/ frontend/tests/unit/ToolPill.test.tsx
git commit -m "feat(ui): ToolPill — debounced now-playing indicator from tool_events"
```

---

## Task 9: Build `ToolActivityLog` component

**Files:**
- Create: `frontend/components/ToolActivity/ToolActivityLog.tsx`
- Test: `frontend/tests/unit/ToolActivityLog.test.tsx`

The log lists events chronologically. Mode B (contextual) by default; per-row chevron toggles mode C (forensic: full args, WFS URL, copy button).

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/unit/ToolActivityLog.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ToolActivityLog } from "@/components/ToolActivity/ToolActivityLog";
import type { ToolEvent } from "@/lib/types";

const evOk = (overrides: Partial<ToolEvent> = {}): ToolEvent => ({
  id: "te_1",
  tool_call_id: "tc_1",
  tool: "select_features",
  args_summary: "layer=chaussees, predicate=intersects",
  args_raw: { layer: "chaussees", spatial_predicate: "intersects" },
  started_at: 1.0,
  ended_at: 2.5,
  duration_ms: 1500,
  status: "ok",
  result_summary: "142 features → result_007",
  ...overrides,
});

describe("ToolActivityLog", () => {
  it("renders rows in chronological order with B-mode summary", () => {
    const a = evOk({ id: "te_a", tool: "select_features" });
    const b = evOk({ id: "te_b", tool: "filter_attributes", started_at: 3.0 });
    render(<ToolActivityLog events={[a, b]} open onClose={() => undefined} />);
    const rows = screen.getAllByTestId("tool-event-row");
    expect(rows[0]).toHaveTextContent("Sélection de features WFS");
    expect(rows[1]).toHaveTextContent("Filtrage par attribut");
    expect(screen.getByText("142 features → result_007")).toBeInTheDocument();
  });

  it("per-row chevron toggles forensic detail (args_raw, JSON visible)", () => {
    render(<ToolActivityLog events={[evOk()]} open onClose={() => undefined} />);
    expect(screen.queryByText(/intersects/)).toBeInTheDocument(); // args_summary
    expect(screen.queryByText(/"spatial_predicate"/)).toBeNull();   // args_raw hidden initially
    fireEvent.click(screen.getByLabelText(/Détails forensiques/i));
    expect(screen.getByText(/"spatial_predicate"/)).toBeInTheDocument();
  });

  it("shows error code red on error events", () => {
    const err = evOk({
      id: "te_e",
      tool: "select_features",
      status: "error",
      result_summary: undefined,
      error: { code: "wfs_error", message: "boom" },
    });
    render(<ToolActivityLog events={[err]} open onClose={() => undefined} />);
    expect(screen.getByText(/wfs_error/)).toBeInTheDocument();
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    const { container } = render(<ToolActivityLog events={[evOk()]} open={false} onClose={() => undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npm test -- ToolActivityLog
```

Expected: import error.

- [ ] **Step 3: Build the log component**

Create `frontend/components/ToolActivity/ToolActivityLog.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { ToolEvent } from "@/lib/types";
import { humanise } from "./humanise";

interface Props {
  events: ToolEvent[];
  open: boolean;
  onClose: () => void;
}

export function ToolActivityLog({ events, open, onClose }: Props) {
  if (!open) return null;
  return (
    <div
      data-testid="tool-activity-log"
      style={{
        position: "fixed",
        bottom: 80,
        right: 24,
        width: 480,
        maxHeight: 520,
        overflow: "auto",
        background: "#0f172a",
        color: "#e2e8f0",
        borderRadius: 8,
        padding: 12,
        fontFamily: "system-ui",
        fontSize: 12,
        boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
        zIndex: 1000,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", marginBottom: 8 }}>
        <strong style={{ flex: 1 }}>Activité</strong>
        <button
          onClick={onClose}
          style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: 14 }}
          aria-label="Fermer le log"
        >
          ✕
        </button>
      </div>
      {events.length === 0 ? (
        <div style={{ color: "#94a3b8", fontStyle: "italic" }}>Aucune activité pour l'instant.</div>
      ) : (
        events.map((e) => <LogRow key={e.id} event={e} />)
      )}
    </div>
  );
}

function LogRow({ event }: { event: ToolEvent }) {
  const [forensic, setForensic] = useState(false);
  const icon = event.status === "running" ? "⟳" : event.status === "ok" ? "✓" : "✗";
  const colour = event.status === "running" ? "#7dd3fc" : event.status === "ok" ? "#86efac" : "#fca5a5";

  return (
    <div
      data-testid="tool-event-row"
      style={{
        padding: "8px 0",
        borderBottom: "1px solid #1e293b",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ color: colour }}>{icon}</span>
        <strong>{humanise(event.tool)}</strong>
        <span style={{ flex: 1 }} />
        {event.duration_ms !== null && (
          <span style={{ color: "#94a3b8", fontFamily: "monospace" }}>
            {(event.duration_ms / 1000).toFixed(2)}s
          </span>
        )}
        <button
          aria-label="Détails forensiques"
          onClick={() => setForensic((v) => !v)}
          style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer" }}
        >
          {forensic ? "▲" : "▼"}
        </button>
      </div>
      <div style={{ marginTop: 2, fontFamily: "monospace", color: "#94a3b8", fontSize: 11 }}>
        {event.args_summary}
      </div>
      {event.result_summary && (
        <div style={{ marginTop: 2, fontFamily: "monospace", color: "#86efac", fontSize: 11 }}>
          → {event.result_summary}
        </div>
      )}
      {event.error && (
        <div style={{ marginTop: 2, fontFamily: "monospace", color: "#fca5a5", fontSize: 11 }}>
          {event.error.code}: {event.error.message}
        </div>
      )}
      {forensic && (
        <pre
          style={{
            marginTop: 6,
            padding: 8,
            background: "#1e293b",
            borderRadius: 4,
            fontSize: 10,
            overflow: "auto",
          }}
        >
          {JSON.stringify(event.args_raw, null, 2)}
        </pre>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npm test -- ToolActivityLog
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/ToolActivity/ToolActivityLog.tsx frontend/tests/unit/ToolActivityLog.test.tsx
git commit -m "feat(ui): ToolActivityLog — chronological log with B→C forensic toggle"
```

---

## Task 10: Rewrite `MetadataWidget` to drop loading state

**Files:**
- Modify: `frontend/components/Widgets/MetadataWidget.tsx`
- Modify: `frontend/tests/unit/MetadataWidget.test.tsx`

The widget no longer renders a `Chargement…` block. Status prop is removed. If meta is incomplete and REST hydration hasn't landed, the widget returns `null`.

- [ ] **Step 1: Update the failing test first**

In `frontend/tests/unit/MetadataWidget.test.tsx`, replace the existing `it("renders a skeleton when status is executing", …)` test with:

```tsx
  it("renders null when meta is null and no datasetId to hydrate", () => {
    const { container } = render(<MetadataWidget data={undefined} datasetId="" />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText(/Chargement/i)).toBeNull();
  });
```

Then remove the `status="complete"` and `status="executing"` props from every other render call in the same file — `MetadataWidget` no longer takes `status`. For example:

```tsx
render(<MetadataWidget data={META} datasetId="result_002" />);
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npm test -- MetadataWidget
```

Expected: fails (the widget still accepts `status`, and still renders "Chargement…").

- [ ] **Step 3: Drop the loading state**

In `frontend/components/Widgets/MetadataWidget.tsx`:

1. Remove `status` from the `Props` interface.
2. Replace the `if (status === "executing" || status === "inProgress" || !meta) { return <div…>Chargement…</div>; }` block with `if (!meta) return null;`.
3. Remove the `status` parameter from the function signature.

Final shape of the props and gate:

```tsx
interface Props {
  data: Partial<DatasetMetaPayload> | undefined;
  datasetId: string;
  onShowOnMap?: (id: string) => void;
  onFitMap?: (bbox: [number, number, number, number]) => void;
}

// ...inside MetadataWidget:
if (!meta) return null;
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm test -- MetadataWidget
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/Widgets/MetadataWidget.tsx frontend/tests/unit/MetadataWidget.test.tsx
git commit -m "fix(MetadataWidget): drop stuck Chargement… state; return null when empty"
```

---

## Task 11: Replace 3 render hooks with 1 generic + mount `ToolPill` / `ToolActivityLog`

**Files:**
- Modify: `frontend/components/GeoPage.tsx`

The three existing `useCopilotAction({ name: "describe_dataset" | "select_features" | "filter_attributes" })` hooks become a single generic hook covering every dataset-creating tool. The render function pulls the matching dataset from `state.datasets` keyed by `tool_call_id`.

- [ ] **Step 1: Replace the three hooks with seven (one per dataset-creating tool)**

In `frontend/components/GeoPage.tsx`, remove the three existing `useCopilotAction` blocks for `describe_dataset`, `select_features`, `filter_attributes`. Replace them with seven explicit `useCopilotAction` calls — one per tool that creates a dataset. This keeps the hooks order stable for React without an eslint-disable.

Define a shared render function once, above the hooks:

```tsx
function findDatasetByToolResult(
  datasets: ReadonlyArray<{ id: string; tool_call_id?: string | null }>,
  result: unknown,
): { id: string } | null {
  if (!result || typeof result !== "object") return null;
  const r = result as { dataset_id?: string; id?: string };
  const targetId = r.dataset_id ?? r.id;
  if (!targetId) return null;
  return datasets.find((d) => d.id === targetId) ?? null;
}

const renderDatasetResult = (name: string) =>
  ({ result, status }: { result: unknown; status: string }) => {
    if (status === "executing" || !result) return null;
    const ds = findDatasetByToolResult(agentState?.datasets ?? [], result);
    // describe_dataset returns the full meta as result; if it's not in state.datasets
    // (because the tool doesn't create a new dataset, it inspects an existing one),
    // render the payload directly.
    if (!ds && name === "describe_dataset") {
      const r = result as { id?: string };
      if (!r.id) return null;
      return (
        <MetadataWidget
          data={result as never}
          datasetId={r.id}
          onShowOnMap={onShowOnMap}
          onFitMap={onFitMap}
        />
      );
    }
    if (!ds) return null;
    return (
      <MetadataWidget
        data={ds as never}
        datasetId={ds.id}
        onShowOnMap={onShowOnMap}
        onFitMap={onFitMap}
      />
    );
  };

useCopilotAction({ name: "describe_dataset",   available: "disabled", render: renderDatasetResult("describe_dataset") });
useCopilotAction({ name: "select_features",    available: "disabled", render: renderDatasetResult("select_features") });
useCopilotAction({ name: "filter_attributes",  available: "disabled", render: renderDatasetResult("filter_attributes") });
useCopilotAction({ name: "aggregate",          available: "disabled", render: renderDatasetResult("aggregate") });
useCopilotAction({ name: "spatial_overlay",    available: "disabled", render: renderDatasetResult("spatial_overlay") });
useCopilotAction({ name: "spatial_join",       available: "disabled", render: renderDatasetResult("spatial_join") });
useCopilotAction({ name: "transform_geometry", available: "disabled", render: renderDatasetResult("transform_geometry") });
```

**Correlation strategy:** the tool_result payload sent in the `ToolMessage` already includes `dataset_id` (or `id` for `describe_dataset`); the matching dataset lives in `agentState.datasets` with the same `id`. No reliance on a CopilotKit-internal `toolCallId` prop. The `tool_call_id` field on `DatasetMetaLite` added in Task 1 remains useful for the activity log's error chip cross-linking (Task 12).

- [ ] **Step 2: Mount `ToolPill` and `ToolActivityLog` in the JSX tree**

Just above `<CopilotSidebar …/>` in the same file, add:

```tsx
import { ToolPill } from "@/components/ToolActivity/ToolPill";
import { ToolActivityLog } from "@/components/ToolActivity/ToolActivityLog";
// ...
const [logOpen, setLogOpen] = useState(false);
const toolEvents = (agentState as { tool_events?: ToolEvent[] } | undefined)?.tool_events ?? [];
// ...
<div
  style={{ position: "fixed", bottom: 80, right: 24, display: "flex", alignItems: "center", gap: 8, zIndex: 999 }}
>
  <ToolPill events={toolEvents} />
  {toolEvents.length > 0 && (
    <button
      onClick={() => setLogOpen((v) => !v)}
      style={{
        background: "#fff",
        border: "1px solid #cbd5e1",
        borderRadius: 999,
        padding: "4px 10px",
        fontSize: 11,
        cursor: "pointer",
        boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
      }}
    >
      {toolEvents.length} étapes ▾
    </button>
  )}
</div>
<ToolActivityLog events={toolEvents} open={logOpen} onClose={() => setLogOpen(false)} />
```

Add the `import type { ToolEvent } from "@/lib/types"` at the top of the file.

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Smoke-run the dev server**

```bash
cd frontend && npm run dev
```

Open http://localhost:3000, draw a zone, ask for chaussées. Confirm:
- The pill appears within ~200ms of clicking send and disappears after the tool returns.
- A dataset card appears in the chat as each tool completes.
- The "X étapes ▾" button toggles the log panel.
- Wait 5s after a turn and verify no "Chargement…" text anywhere in the DOM (`document.body.innerText.includes("Chargement")` returns false).

Stop the dev server.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/GeoPage.tsx
git commit -m "feat(GeoPage): single generic render hook; mount ToolPill + ToolActivityLog"
```

---

## Task 12: Simplify the error chip rendered by `useCoAgentStateRender`

**Files:**
- Modify: `frontend/components/GeoPage.tsx`

- [ ] **Step 1: Replace the error block**

In the `useCoAgentStateRender` block, replace the multi-line error rendering with a compact chip. Find the existing block:

```tsx
{lastErr ? (
  <div style={{ color: "red" }}>
    <strong>Erreur ({lastErr.code}) :</strong> {lastErr.message}
    {lastErr.suggestion ? <div style={{ opacity: 0.8 }}>↳ {lastErr.suggestion}</div> : null}
  </div>
) : null}
```

Replace with:

```tsx
{lastErr ? (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      background: "#fef2f2",
      color: "#b91c1c",
      border: "1px solid #fecaca",
      borderRadius: 4,
      padding: "4px 8px",
      fontSize: 12,
    }}
  >
    <span>⚠️</span>
    <strong style={{ fontFamily: "monospace" }}>{lastErr.code}</strong>
    <span style={{ opacity: 0.8 }}>{lastErr.message}</span>
  </div>
) : null}
```

The full message and suggestion remain visible in the activity log's forensic view (the matching `tool_events` entry has the same `tool_call_id`).

- [ ] **Step 2: Manual smoke test**

```bash
cd frontend && npm run dev
```

Trigger an error (e.g. ask the agent to find features in a non-existent layer). Verify the chip is compact and red.

Stop the dev server.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/GeoPage.tsx
git commit -m "refactor(GeoPage): compact error chip — details now in activity log"
```

---

## Task 13: Delete `AnalysisProgress.tsx`

**Files:**
- Delete: `frontend/components/AgentStateRenderers/AnalysisProgress.tsx`

- [ ] **Step 1: Verify no references**

```bash
cd frontend && grep -rn "AnalysisProgress" .
```

Expected: only the file itself. If anything else references it, stop and update those callers — the spec says this file is unused.

- [ ] **Step 2: Delete and verify build**

```bash
rm frontend/components/AgentStateRenderers/AnalysisProgress.tsx
rmdir frontend/components/AgentStateRenderers 2>/dev/null || true
cd frontend && npx tsc --noEmit && npm test -- --run
```

Expected: type-check and all unit tests pass.

- [ ] **Step 3: Commit**

```bash
git add -A frontend/components/AgentStateRenderers/
git commit -m "chore(ui): remove unused AnalysisProgress.tsx"
```

---

## Task 14: End-to-end Playwright test

**Files:**
- Create: `frontend/tests/e2e/tool-feedback.spec.ts`

Validate the integrated flow: pill appears, dataset card lands before the LLM finishes, and no stuck "Chargement…" exists 5s after turn completion.

- [ ] **Step 1: Write the spec**

Create `frontend/tests/e2e/tool-feedback.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

test.describe("tool-feedback", () => {
  test("pill appears, dataset card lands during turn, no stuck Chargement", async ({ page }) => {
    await page.goto("/");
    // Wait for the sidebar to render
    await expect(page.locator(".copilotKitInput textarea")).toBeVisible({ timeout: 10000 });

    // Draw a small zone in the middle of the viewport
    await page.getByRole("button", { name: /Dessiner zone/i }).click();
    const map = page.locator("canvas").first();
    const box = await map.boundingBox();
    if (!box) throw new Error("no map canvas");
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await page.mouse.click(cx - 60, cy - 60);
    await page.mouse.click(cx + 60, cy - 60);
    await page.mouse.click(cx + 60, cy + 60);
    await page.mouse.click(cx - 60, cy + 60);
    await page.mouse.dblclick(cx - 60, cy - 60);

    // Send a chat message
    await page.locator(".copilotKitInput textarea").fill("Trouve les chaussées dans cette zone");
    await page.keyboard.press("Enter");

    // Pill should appear within 3s
    await expect(page.getByRole("status").filter({ hasText: /Sélection|Filtrage|Inspection|Liste|Agrégation/i })).toBeVisible({ timeout: 3000 });

    // At least one dataset card should land in the chat before 30s
    await expect(page.locator("text=DATASET").first()).toBeVisible({ timeout: 30000 });

    // Wait 5s after no more activity, then assert "Chargement…" is absent
    await page.waitForTimeout(5000);
    const stuck = await page.evaluate(() => document.body.innerText.includes("Chargement"));
    expect(stuck).toBe(false);
  });
});
```

- [ ] **Step 2: Run the spec**

```bash
cd frontend && npm run test:e2e -- tool-feedback
```

Expected: PASS. (The test assumes a backend reachable at the default URL — start it in a separate terminal: `cd backend && uv run uvicorn geo_agent.main:app --reload`.)

If the WFS query times out or returns no features, broaden the test zone or pick a different layer. The assertion target is the *behaviour*, not a specific layer's data.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/tool-feedback.spec.ts
git commit -m "test(e2e): pill, progressive datasets, no stuck Chargement…"
```

---

## Final verification

After all tasks pass individually, run the complete suite:

```bash
cd backend && uv run pytest
cd ../frontend && npm test -- --run && npx tsc --noEmit
cd frontend && npm run test:e2e -- tool-feedback
```

All green ⇒ ship. The user gets:

- a pill that shows what the agent is doing, right above the input;
- a dataset card per tool, appearing as each one finishes;
- no more "Chargement…" stuck anywhere;
- chat prose that doesn't recite what the widget already shows.

---

## Out of scope (do NOT add)

- The bottom `DatasetPanel` (unchanged).
- Map components, drawing, feature inspector.
- New tools or changes to the tool catalog.
- Threading model, persistence, session isolation.
- LLM provider switching.
