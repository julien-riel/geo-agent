# Geo-agent UI feedback — design

**Date:** 2026-05-13
**Scope:** Replace the silent / stuck "Chargement…" widget pattern with a unified tool-activity feed (a "now playing" pill + collapsible activity log) backed by a new `tool_events` state channel, surface every backend tool invocation in the UI (WFS calls, spatial ops, dataset ops), strip data-duplicating prose out of the agent's chat by tightening the system prompt and the `ToolMessage` payloads, and ensure dataset cards appear in the chat as each tool completes (not at end-of-turn).

## 1. Goal

The current chat surface has four interlocking UX problems:

1. **"Chargement…" widgets that never resolve.** `MetadataWidget` shows `<em>Chargement…</em>` whenever its `status` is `"executing"` or its `meta` is incomplete. Several paths leave the widget stuck: a tool result whose payload doesn't satisfy `isCompleteMeta()` (e.g. `select_features` returns `{dataset_id, alias, feature_count, bbox, attribute_schema}` — no `lineage`, no `source`), an `executing` state where `datasetId=""` so the REST hydrate fallback is gated and never fires, and 12 of the 15 backend tools that don't have a `useCopilotAction({ render })` at all and may surface a default "loading…" placeholder from CopilotKit.
2. **No visibility on what the backend is doing.** When the agent calls `list_wfs_layers`, `describe_wfs_layer`, `select_features`, or a spatial operation chain, the user sees nothing until the LLM emits prose. For a multi-step plan (8–10 tool calls is not unusual), this means seconds of silence followed by a wall of widgets.
3. **Chat prose duplicates widget data.** The agent often writes "I found 142 features in chaussees_zone, with bbox [...]" right next to the dataset card that already shows the same information. This is partly a prompt issue and partly a `ToolMessage` issue: every dataset-creating tool returns a result payload rich enough for the model to recite back.
4. **Datasets only appear after the turn finishes.** The `merge_datasets` reducer is in place and tool returns a `Command(update={"datasets": [...]})`, so in theory each step pushes a state delta — but the inline widget reads the tool result rather than the state, creating a race where the dataset card and the bottom panel can land at different times, and the visible progressive behaviour is not reliable.

This design adds:

- a new `tool_events` channel on `AgentState` (capped at 50 entries) populated by an `@instrumented_tool` decorator that wraps every backend tool;
- two new frontend components — `ToolPill` (a 150ms-debounced "now playing" indicator pinned above the chat input) and `ToolActivityLog` (a collapsible log with a per-row B-contextual / C-forensic toggle);
- a rewrite of the inline `MetadataWidget` so it no longer renders a stuck "Chargement…" — it now hydrates from `state.datasets` keyed by `tool_call_id`, and returns `null` when data is missing rather than a loading placeholder;
- a `# Communication style` section at the top of the system prompt that forbids restating widget-visible data;
- a payload trim on every dataset-creating tool's `ToolMessage`, removing fields (`bbox`, `attribute_schema`, …) that exist only to be re-read by the model and never used by it for decisions.

## 2. Backend

### 2.1 `tool_events` channel on `AgentState`

`backend/geo_agent/agent/state.py` gains a new channel and reducer:

```python
TOOL_EVENTS_CAP = 50

def append_tool_events(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Append tool lifecycle events. Newest entries with the same `id`
    overwrite older ones (start → end transitions)."""
    by_id: dict[str, dict[str, Any]] = {e["id"]: e for e in (left or [])}
    for e in right or []:
        by_id[e["id"]] = e
    merged = list(by_id.values())
    return merged[-TOOL_EVENTS_CAP:]


class AgentState(TypedDict):
    ...
    tool_events: Annotated[list[dict[str, Any]], append_tool_events]
```

The reducer is **keyed by `id`** (not append-only) because a single tool call produces two writes: a `running` event at start and an `ok`/`error` event at end. The second write overwrites the first on the same `id`. Total capacity stays at 50 distinct events.

Event payload:

```python
{
  "id": "te_<uuid7>",            # stable react key, also used for start→end overwrite
  "tool_call_id": "<langchain tool_call_id>",  # to correlate with datasets
  "tool": "select_features",
  "args_summary": "layer=chaussees, predicate=intersects, zone=drawing_a4f",
  "args_raw": {...},             # original kwargs, for forensic view (omit InjectedState)
  "started_at": 1778699400.123,  # epoch seconds, monotonic.ish (perf_counter offset)
  "ended_at": 1778699402.045,    # null while running
  "duration_ms": 1922,           # null while running
  "status": "running" | "ok" | "error",
  "result_summary": "142 features → chaussees_zone",   # only when status != running
  "error": {"code": "wfs_error", "message": "..."}     # only when status == error
}
```

### 2.2 `@instrumented_tool` decorator

New file `backend/geo_agent/agent/tools/_instrumentation.py`. Wraps `langchain_core.tools.tool` so the existing 15 `@tool` declarations only change their import line.

Behaviour:

1. On invoke, generate `event_id = "te_" + uuid7()`, capture `started_at`, build a `running` event, write it as a "pre-update" via LangGraph's streaming `writer` (so the pill appears before the tool returns).
2. Call the wrapped function inside a `try`.
3. On success:
   - if the tool returned a `Command`, amend `Command.update["tool_events"] = [final_event]` (final event has same `id`, `status="ok"`, `ended_at`, `duration_ms`, `result_summary`);
   - if the tool returned a scalar / dict (LangChain will wrap it as a `ToolMessage`), build the equivalent `Command(update={"messages": [ToolMessage(content=..., tool_call_id=...)], "tool_events": [final_event]})` and return it instead.
4. On exception: build event with `status="error"`, `error={"code": "internal_error", "message": str(exc)}`, append, and re-raise so LangGraph's normal error handling still runs. Tools that already produce a `tool_error_command` (the project's pattern) take precedence — the decorator's exception path only fires on uncaught throws.

The decorator delegates `args_summary` and `result_summary` formatting to a per-tool summarizer table; fallback is `repr(args)[:80]` / `repr(result)[:120]`. Summarizers live in the same file, one function per tool:

```python
SUMMARIZERS: dict[str, Callable[[dict, Any], tuple[str, str]]] = {
    "select_features": _sum_select_features,
    "filter_attributes": _sum_filter_attributes,
    "describe_wfs_layer": _sum_describe_wfs_layer,
    # ...one per tool, fallback is _sum_default
}
```

`args_raw` strips injected runtime args (`tool_call_id`, `state`) so the forensic view shows only what a human would have typed.

### 2.3 Streaming the "running" event (pre-update)

LangGraph exposes `langgraph.config.get_stream_writer()` — a function callable from inside a tool that writes a custom event into the agent's stream. CopilotKit's LangGraph integration forwards "values" stream events into the React agent state. The decorator uses the writer like:

```python
from langgraph.config import get_stream_writer

def _emit_running(event: dict) -> None:
    try:
        writer = get_stream_writer()
    except Exception:
        return  # non-streaming context (tests, scripts) — silently skip
    writer({"tool_events": [event]})
```

**Integration risk to validate during implementation:** whether CopilotKit's `useCoAgent` receives `tool_events` deltas from custom-stream writes, not just from final `Command` updates. The straightforward path is to test this with a 2s tool and watch the frontend. If it works → pill shows live during execution. If not → **Plan B**: the running event is dropped and only the final event (delivered by the `Command.update` after the tool returns) is rendered. The pill then only appears for the *next* tool in a chain (you see the previous one completing in the log while the next one starts running). The system still works — we just lose the live in-flight indicator for the first tool of each turn. This fallback is acceptable for the POC.

Both paths use the same event payload and the same reducer, so the rest of the design (frontend components, log, narrative) is unaffected.

### 2.4 Tool integration

`backend/geo_agent/agent/tools/__init__.py` is unchanged — no rename of the 15 tool symbols. Each individual tool file changes one import:

```python
# Before
from langchain_core.tools import tool
# After
from geo_agent.agent.tools._instrumentation import instrumented_tool as tool
```

The 15 `@tool` lines stay as-is. Total LOC change in tool files: 15 lines (one import each).

### 2.5 `ToolMessage` payload trim

The `tool_result` JSON passed back to the model (via `ToolMessage.content`) is shrunk for every dataset-creating tool. Today, `select_features` returns:

```python
{"dataset_id", "alias", "feature_count", "bbox", "attribute_schema"}
```

After:

```python
{"dataset_id", "alias", "feature_count"}
```

`bbox` stays available to the widget because `DatasetMetaLite` (what lands in `state.datasets`) already carries it. `attribute_schema` is **not** in `DatasetMetaLite` — the `MetadataWidget` keeps its existing REST hydration path (`GET /api/datasets/{id}/meta`) for the rare case when the user clicks "Voir le schéma". The model regains the same data through `describe_dataset` if it needs to plan a subsequent filter. The same trim applies to:

- `filter_attributes` — drop `bbox`, `attribute_schema`.
- `spatial_overlay`, `spatial_join`, `transform_geometry` — drop `bbox`, `attribute_schema`.
- `aggregate` — already returns only `{op, value, group_by?}`, no change.
- `describe_dataset` — unchanged; the model uses its full output.

The widget never reads from the `ToolMessage` after this change — it reads `state.datasets` keyed by `tool_call_id`. See §3.3.

### 2.6 System-prompt update

A new `# Communication style` section is inserted in `backend/geo_agent/agent/prompts.py` between `# Role` and `# Core rules`. Verbatim text:

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

## 3. Frontend

### 3.1 New components

#### `ToolPill` (`frontend/components/ToolActivity/ToolPill.tsx`)

- Mounted inside `GeoPage`, rendered as an overlay pinned ~8px above the `CopilotSidebar`'s input area (CSS `position: fixed` with z-index above the sidebar, positioned via the sidebar's input bounding rect — measured once on open).
- Reads `agentState.tool_events`. Finds the last entry whose `status === "running"`. If none, renders `null`.
- Anti-flash: 150ms appearance delay, 100ms disappearance delay (via `useEffect` setTimeout). For tools < 100ms the pill never appears.
- Content: spinner icon + humanised tool name (lookup table: `select_features` → "Sélection de features WFS", etc.) + live elapsed-time counter (updates every 250ms while running).
- Right side: a small `"X étapes ▾"` button whose count is `tool_events.length`. Clicking opens the `ToolActivityLog`.
- Stalled state: if `status === "running"` and `Date.now() - started_at*1000 > 60_000`, the pill turns amber with text "L'opération prend plus longtemps que prévu".
- Error state: when an event transitions to `status === "error"`, the pill briefly shows the error code in red for 2s before resolving to whatever is next-running (or disappearing).

#### `ToolActivityLog` (`frontend/components/ToolActivity/ToolActivityLog.tsx`)

- A drawer/popover anchored to the pill's "X étapes ▾" button. Opens upward (chat sidebar is bottom-anchored). Width = pill width minimum, expandable up to 480px.
- Default closed. Persists open/closed state to `sessionStorage` so it survives reloads within a thread.
- Body: list of `tool_events`, **chronological** (oldest first), one row per event.
- Each row in **mode B (contextual)** by default:
  - status icon (`⟳ / ✓ / ✗`) — colour-coded;
  - tool name (humanised, bold);
  - `args_summary` (monospace, muted);
  - `result_summary` (monospace, green) when `ok`, or `error.code: error.message` (monospace, red) when `error`;
  - elapsed time on the right.
- Per-row chevron toggles **mode C (forensic)** for that row only:
  - full `args_raw` JSON (pretty-printed, monospace);
  - if the event is for a WFS tool, the generated request URL (resolved from `args_raw`) with a "📋 Copier" button;
  - approximate response size (if available);
  - retry hints / linked dataset IDs.
- Header has a "🔍 Tout déplier / Replier" toggle that applies forensic mode to every row at once.
- If `tool_events.length` is capped (50 reached), the top of the list shows a divider `… anciennes étapes tronquées`.

### 3.2 `MetadataWidget` changes

`frontend/components/Widgets/MetadataWidget.tsx`:

- Remove the `if (status === "executing" || status === "inProgress" || !meta) return <em>Chargement…</em>` block. Replace with `if (!meta) return null`.
- Remove `status` from the props entirely (no longer used).
- Keep the `datasetId` prop and the existing REST hydration via `GET /api/datasets/{id}/meta` — it remains the only path to obtain `attribute_schema` for the "Voir le schéma" action.
- The widget can be assumed to only mount when there's data to show. If the data hydration race wins, the widget appears slightly later — better than a stuck placeholder.

### 3.3 Inline dataset card rendering

Today, `GeoPage.tsx` registers three `useCopilotAction({ available: "disabled", render })` hooks for `describe_dataset`, `select_features`, `filter_attributes`. Each reads the tool result and renders a `MetadataWidget`.

New approach: a **single generic render hook** registered for every dataset-creating tool (`describe_dataset`, `select_features`, `filter_attributes`, `aggregate` if it creates a dataset, `spatial_overlay`, `spatial_join`, `transform_geometry`). The render function:

1. Reads the `tool_call_id` from the action context (CopilotKit provides this).
2. Looks up `agentState.tool_events.find(e => e.tool_call_id === toolCallId && e.status === "ok")`.
3. From that event, reads `result_summary` (which contains the created dataset id) — or, more robustly, reads the most-recently-added entry to `agentState.datasets` whose creation correlates with this tool call. We add a `tool_call_id` field to `DatasetMetaLite` in the in-state representation (frontend-only enrichment) to make the lookup deterministic.

Pragmatic implementation: `dataset_created_command` (in `backend/geo_agent/agent/error_helpers.py`) already receives `tool_call_id` and already serializes `meta.model_dump(mode="json")` before appending to `state.datasets`. We add a `tool_call_id: str | None = None` field to `DatasetMetaLite` (Pydantic model in `backend/geo_agent/models.py`); `dataset_created_command` sets it before serialization. The frontend then matches on `dataset.tool_call_id`. `DatasetMetaLite` consumers that don't care about this field (the bottom `DatasetPanel`, REST hydration of pre-existing datasets) ignore it without change.

4. If no matching dataset is found (tool errored, or hasn't completed yet), render `null` — the pill / log handles user feedback.
5. If a match is found, render `<MetadataWidget data={dataset} onShowOnMap={…} onFitMap={…} />`.

This removes all three existing render hooks, the duplicate logic between them, and the fragile fallback to `/api/datasets/{id}/meta` from the widget.

### 3.4 Error chip simplification

The `useCoAgentStateRender` block in `GeoPage.tsx` currently renders `state.errors[last]` as:

```jsx
<div style={{ color: "red" }}>
  <strong>Erreur ({code}) :</strong> {message}
  <div style={{ opacity: 0.8 }}>↳ {suggestion}</div>
</div>
```

After: a compact red chip — `⚠️ {code}` — with an inline "voir détails" link that scrolls/opens the `ToolActivityLog` to the matching event (events and errors share `tool_call_id`). The full message and suggestion are visible in the log's forensic view.

### 3.5 Removal

- Delete `frontend/components/AgentStateRenderers/AnalysisProgress.tsx` (unused, redundant with `ToolPill`).
- Remove the three existing `useCopilotAction` render hooks for `describe_dataset`, `select_features`, `filter_attributes` in `GeoPage.tsx`. Replace with the single generic hook described in §3.3.

### 3.6 Not changed

The following stay as-is:

- `DatasetPanel` at the bottom of the page (already reflects `state.datasets` correctly).
- `FeatureDrawer`, `FeaturePopup`, `HighlightLayer`, `DrawTool`, `MapView`.
- `InspectDatasetWidget` (rendered from `state.inspections` via `useCoAgentStateRender`; the pill will show during `inspect_dataset` execution, but the widget itself is independent).
- The `SchemaWidget`, `FeatureListWidget`, `FeatureWidget`, `AttributeStatsRow` widgets.

## 4. Data flow at runtime

For a user request like *"Trouve les chaussées dans cette zone, garde celles de plus de 200m, affiche-les"*:

1. LLM emits a `select_features` tool call.
2. `@instrumented_tool` writes `{id: te_1, status: "running", tool: "select_features", ...}` via `writer({"tool_events": [...]})`. CopilotKit streams the state delta. Frontend `ToolPill` debounces; if the call takes > 150ms, the pill appears.
3. Tool returns `Command(update={"messages": [...], "datasets": [...], "tool_events": [{id: te_1, status: "ok", ...}]})`. The reducer overwrites `te_1` (id-keyed) with the final event and appends the new dataset.
4. Frontend gets the delta: `tool_events[te_1]` is now `ok`; pill disappears (or transitions to next running event); `MetadataWidget` for `tool_call_id` finds its dataset and renders inline.
5. LLM emits `filter_attributes` tool call. Repeat 2–4. The `DatasetPanel` at the bottom shows two rows (`chaussees_zone`, `chaussees_longues`) live.
6. LLM emits `show_on_map`. Pill shows briefly; the `DatasetLayer` mounts on the map.
7. LLM finishes the turn with one sentence: "Voilà, 53 chaussées correspondent — j'ai zoomé dessus."

No "Chargement…" anywhere. The user has a live pill, an expandable log, and dataset cards that appeared as each tool completed.

## 5. Edge cases

| Case | Handling |
|---|---|
| Tool returns < 100ms | Pill never shows (150ms debounce). Event still lands in the log. |
| Tool hangs > 60s | Pill turns amber, shows "L'opération prend plus longtemps que prévu". No auto-cancel. |
| Tool throws uncaught | Decorator catches, writes `status="error"` event with `code="internal_error"`, re-raises. |
| Tool returns a `tool_error_command` | Decorator amends the existing `Command` with `tool_events` final event (`status="error"`, `error` from `ToolError`). |
| Page reload mid-tool | `MemorySaver` preserves `tool_events`; on re-mount, pill picks up any `running` event. 60s timeout protects against ghost-running events. |
| 50-event cap reached | Reducer drops oldest. Log shows a `… anciennes étapes tronquées` divider. |
| Tool with no dataset output (`list_wfs_layers`, `inspect_dataset`, `show_on_map`) | Pill + log entry, no inline `MetadataWidget`. |
| Tool result missing summarizer | Fallback `repr(args)[:80]` / `repr(result)[:120]`. Log row still informative. |

## 6. Testing

| Level | Test | Asserts |
|---|---|---|
| Backend unit | `test_instrumentation.py` | Decorator captures `started_at`/`ended_at`; running + ok events have same `id`; exception path writes error event with `code="internal_error"`; `Command` amendment merges with existing `update` without dropping `datasets`/`messages`. |
| Backend unit | `test_state_reducer.py::append_tool_events` | Cap at 50; id-keyed overwrite (start→end on same id collapses to one event); chronological order preserved across overwrites. |
| Backend integration | `test_graph_tool_events.py` | A `select_features` invocation produces exactly one final event with `status="ok"`, correct `tool_call_id`, `args_summary` populated. WFS error path → `status="error"` with `error.code="wfs_error"`. |
| Backend integration | `test_dataset_command_correlation.py` | `dataset_created_command` writes `tool_call_id` into the `DatasetMetaLite` entry; the entry is correlatable to the matching `tool_events` row. |
| Frontend unit | `ToolPill.test.tsx` | Anti-flash 150ms / disappearance 100ms; renders null when no running event; humanised label; elapsed-time counter increments; stalled state at 60s. |
| Frontend unit | `ToolActivityLog.test.tsx` | Per-row B→C toggle reveals `args_raw` + WFS URL; chronological order; truncation divider at cap; sessionStorage persistence. |
| Frontend unit | `MetadataWidget.test.tsx` | Returns `null` when `meta` is `null` (no "Chargement…" string in DOM). |
| E2E Playwright | `tests/tool-feedback.spec.ts` | Draw zone → ask for chaussées → pill appears → dataset card appears before the LLM finishes → pill disappears → log has the expected event. |
| E2E Playwright (regression) | Same spec | After 5s of inactivity post-turn, no "Chargement…" string in the DOM. |

## 7. Migration & rollout

The change is internal to the agent / chat surface. No data migration. No HTTP API changes. The `ToolMessage` payload trim could in principle hurt a model that depended on `bbox`/`attribute_schema` in the result — mitigation: it can still call `describe_dataset` to get them, and the system-prompt updates already steer the model toward narrating widget-shown data less, not analysing it less.

Sequence:

1. Backend: add `tool_events` channel + decorator + summarizers (no UI change yet; pills don't appear because the frontend doesn't read the channel). Verify backend tests pass.
2. Backend: trim `ToolMessage` payloads. Verify graph integration tests still pass with the trimmed payloads (the model receives less, but the project's existing scenario tests should not depend on `bbox`/`attribute_schema` in tool results — verify).
3. Frontend: add `ToolPill` + `ToolActivityLog`. Pills become visible. Old `MetadataWidget` "Chargement…" path is still live.
4. Frontend: replace the three `useCopilotAction` hooks with the generic one; rewrite `MetadataWidget` to drop the loading state.
5. Prompt: add `# Communication style` section.
6. Cleanup: delete `AnalysisProgress.tsx`.

Each step is independently testable and ships behind no flag — failures are user-visible immediately, which is acceptable for this single-user POC.

## 8. Out of scope

- The bottom `DatasetPanel` UI (already works; not touching it).
- Map components, drawing, feature inspection drawer.
- New tools or changes to the 15-tool catalog.
- Threading model, persistence layer, or session isolation.
- Migration between LLM providers (orthogonal).
- Internationalisation of pill / log labels beyond the existing French / English mix.
