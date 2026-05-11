# Dataset management — design

**Date:** 2026-05-11
**Scope:** Add three agent-callable tools to manage local datasets (`delete_dataset`, `rename_dataset`, `clear_all_datasets`), a `DELETE /datasets` HTTP route wired to the "Nouvelle conversation" button, and a UI revamp of the bottom dataset panel: per-row delete and inline rename, a "Tout effacer" button in the panel header, grouping by operation type, icons, and parent lineage indication.

## 1. Goal

Datasets currently accumulate indefinitely in `backend/data/results/`. There is no agent path to remove or rename them, the "Nouvelle conversation" button resets the thread id but leaves every previous dataset visible (the frontend hydrates from `/datasets` on mount), and the bottom panel offers only a checkbox per row — no way to delete, rename, or clear from the UI. Three consequences:

1. The dataset panel grows monotonically across sessions; the result store has no isolation by design (POC), so the only way back to a clean state today is `rm -rf backend/data/results/*`.
2. The agent cannot recover from its own mistakes — a bad `select_features` call leaves a useless dataset that bloats the list re-injected into the system prompt every turn (see `prompt_builder.format_datasets_summary`).
3. The user cannot fix mistakes either: aliases are immutable, rows cannot be deleted without dropping out to a shell, and there is no visible cue that a dataset came from another one (lineage is on disk but never surfaced).

This design adds:

- three agent tools that mirror the operations already implemented on `ResultStore` (`delete`, `update_alias`), plus one for bulk-clear;
- three new HTTP routes (`DELETE /datasets`, `DELETE /datasets/{id}`, `PATCH /datasets/{id}`) so the UI does not need to go through the agent for routine maintenance;
- a system-prompt guard so the local model does not call `clear_all_datasets` on its own initiative;
- a UI revamp of `DatasetPanel`: per-row trash + inline-rename, a panel-header "Tout effacer" button, grouping by operation type with icons, and a parent-lineage line under derived datasets.

## 2. Tool catalog (3 new tools)

All three live under `backend/geo_agent/agent/tools/datasets/` and follow the existing conventions (LangChain `@tool` decorator, `InjectedToolCallId` + `InjectedState`, return a `Command` for both success and error). Tool count goes from 12 to 15.

### 2.1 `delete_dataset(id_or_alias)`

Resolves `id_or_alias` through `services.store` (which already accepts both via `_resolve_id`), calls `store.delete()`, and returns a `Command` that:

- removes the entry from `AgentState.datasets`,
- removes the id from `AgentState.active_layers` if it was active there,
- emits a `ToolMessage` with `{"deleted": <resolved_id>}`.

On a miss, returns `dataset_not_found_command(...)` (helper exists in `error_helpers.py`). No new error code.

Lineage is not preserved (the dataset is gone); downstream datasets that referenced it through `lineage.parent_ids` are not cascaded — that is intentional. The user/agent can chain `list_datasets` (via the prompt summary) to spot orphans.

### 2.2 `rename_dataset(id_or_alias, new_alias)`

Validates the new alias:

- non-empty, no whitespace, max 64 chars (regex `^\S{1,64}$`),
- not already used by another dataset.

On success: `store.update_alias(rid, new_alias)`, returns `Command` that replaces the entry in `AgentState.datasets` with the patched copy and emits `{"id": rid, "alias": new_alias}`.

Errors:

- `dataset_not_found` — same helper as above.
- `bad_input` — empty / whitespace / too-long alias, with `suggestion` describing the rule.
- `alias_conflict` — **new error code**. Suggestion: `"alias '<new_alias>' is already used by <existing_id>; pick another"`.

### 2.3 `clear_all_datasets()`

No arguments. Lists every dataset, deletes each via `store.delete()`, and returns a `Command` that sets `AgentState.datasets = []` and `AgentState.active_layers = []`, emitting `{"deleted": <count>}`.

Idempotent — calling on an empty store returns `{"deleted": 0}` with no error.

### 2.4 System-prompt guard

`backend/geo_agent/agent/prompts.py` gains a short stanza near the "Tool catalog" section (in French to match the rest of the prompt):

> `clear_all_datasets` est destructif et irréversible. Ne l'appelle **jamais** sans une demande explicite de l'utilisateur (ex. « efface tous les datasets », « repars de zéro »). En cas de doute, demande confirmation par message — n'appelle pas le tool.

`delete_dataset` and `rename_dataset` do not get a guard — they are scoped (single id) and reversible by re-running the upstream query, so a stricter rule would unnecessarily handcuff the agent.

### 2.5 Tool registration

`backend/geo_agent/agent/tools/__init__.py` is updated:

- imports for the three new tools,
- entries in `ALL_TOOLS` under the "Local dataset tools" block (right after `describe_dataset`, before `spatial_overlay`),
- entries in `__all__`.

`list_datasets` remains unregistered, as today.

## 3. HTTP routes

Three new routes in `backend/geo_agent/routes/datasets.py`. All three are *separate* code paths from their agent-tool counterparts: the tools participate in the agent loop and push `AgentState`; the routes are plain REST handlers the frontend hits directly. They share `store.delete()` / `store.update_alias()` at the bottom, and that is the only shared part — splitting a private helper would be over-engineering for one or two lines.

### 3.1 `DELETE /datasets`

Used by the panel-header "Tout effacer" button and by the chat-header "Nouvelle conversation" button.

```python
@router.delete("")
def clear_all() -> dict:
    services = get_services()
    ids = [m.id for m in services.store.list()]
    for i in ids:
        services.store.delete(i)
    return {"deleted": len(ids)}
```

### 3.2 `DELETE /datasets/{id}`

Used by the per-row trash button.

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

### 3.3 `PATCH /datasets/{id}`

Used by inline-rename. Body: `{alias: string}`. Same validation rules as the `rename_dataset` tool: non-empty, no whitespace, max 64 chars, no collision with another dataset's alias.

```python
class AliasPayload(BaseModel):
    alias: str

@router.patch("/{dataset_id}")
def rename(dataset_id: str, payload: AliasPayload) -> dict:
    services = get_services()
    new_alias = payload.alias
    if not new_alias or not new_alias.strip() or any(c.isspace() for c in new_alias) or len(new_alias) > 64:
        raise HTTPException(400, "alias must be non-empty, contain no whitespace, and be at most 64 chars")
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

Note the `_resolve_id` call: the route accepts both id and alias in the path, matching the agent tool. Reaching into a private method is acceptable here — the alternative is a public `resolve_id` on the protocol, which is a wider change for a single caller.

### 3.4 Frontend proxies

`frontend/app/api/datasets/route.ts` gains a `DELETE` handler that forwards to `${BACKEND_URL}/datasets`.

`frontend/app/api/datasets/[id]/route.ts` (new file) handles `DELETE` and `PATCH` and forwards to `${BACKEND_URL}/datasets/{id}` with method and body preserved.

### 3.5 `onNewConversation` and panel-header "Tout effacer"

`frontend/components/GeoPage.tsx`, `onNewConversation`:

```ts
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

A second handler, `onClearDatasets` (new), is passed into `DatasetPanel` for the in-panel button:

```ts
const onClearDatasets = async () => {
  if (!window.confirm("Effacer tous les datasets ? La conversation continue.")) return;
  try {
    await fetch("/api/datasets", { method: "DELETE" });
    const current = agentState ?? EMPTY_STATE;
    setAgentState({ ...current, datasets: [], active_layers: [] });
  } catch (e) {
    console.error("clear datasets failed", e);
  }
};
```

Notes:

- The two confirms have different wording: one warns the conversation will reset, the other does not. They are deliberately not unified — the destruction scope is different from the user's point of view, even though the backend operation is identical.
- Failure to clear is logged but does not throw. The panel button leaves stale rows in state on failure; the user can retry. The "Nouvelle conversation" button reloads regardless — a stale dataset list briefly visible on reload is a smaller annoyance than aborting the reset on a 5xx and stranding the user mid-conversation.
- No backend awareness of the thread id is needed; the result store has no session column, so "clear for this thread" and "clear everything" are the same operation.

## 4. Frontend UI revamp (`DatasetPanel`)

### 4.1 Layout

The panel keeps its current position (bottom-left, fixed height, scrollable) and gains a slightly fuller header:

```
┌──────────────────────────────────────────────────────────────┐
│ Datasets (5)              [Dessiner zone] [🗑 Tout effacer]   │
├──────────────────────────────────────────────────────────────┤
│ Zones dessinées (1)                                           │
│   ☐ 📐 zone_1 · 1 feature                          ✎  🗑     │
│                                                                │
│ Résultats WFS (2)                                              │
│   ☑ 🌐 result_001 · 142 features · pyrr:chaussee   ✎  🗑     │
│   ☐ 🌐 result_002 · 87 features · pyrr:batiment    ✎  🗑     │
│                                                                │
│ Dérivés (2)                                                    │
│   ☑ 🔍 result_003 · 23 features                    ✎  🗑     │
│        ← result_001                                            │
│   ☐ ⧉ result_005 · 12 features                     ✎  🗑     │
│        ← result_001, zone_1                                    │
└──────────────────────────────────────────────────────────────┘
```

Three group headers (`<h4>`-style), each with the section's count. Empty groups are hidden. The order is fixed: Zones dessinées → Résultats WFS → Dérivés.

### 4.2 Grouping logic

A pure function `groupDatasets(datasets)` in `DatasetPanel.tsx` maps each row to a group key from its `operation`:

| Group | Operations |
|---|---|
| `zones` | `user_drawing` |
| `wfs` | `select_features` |
| `derived` | everything else (`filter_attributes`, `aggregate`, `spatial_overlay`, `spatial_join`, `transform_geometry`) |

Each group is sorted by id ascending (stable, matches existing order).

### 4.3 Icons

Static mapping in a small `opIcon(op: string): string` helper (still in `DatasetPanel.tsx` for now — colocation with the only call site):

| `operation` | Icon | Source |
|---|---|---|
| `user_drawing` | 📐 | existing |
| `select_features` | 🌐 | new |
| `filter_attributes` | 🔍 | new |
| `aggregate` | Σ | new |
| `spatial_overlay` | ⧉ | new |
| `spatial_join` | ⊕ | new |
| `transform_geometry` | ↻ | new |
| _unknown_ | • | fallback |

Pure emoji + a single Unicode `•` — no new dependency, accessible via `aria-label={operation}`.

### 4.4 Per-row actions

Two icon buttons appear at the right of every row: a pencil (`✎`, rename) and a trash (`🗑`, delete). They are always visible (no hover-reveal — keyboard-discoverable, simpler).

**Delete** — calls `DELETE /api/datasets/{id}`, then on `r.ok` removes the row from `agentState.datasets` and strips the id from `active_layers`. A `window.confirm("Supprimer ce dataset ?")` runs first. On non-OK, log to console and leave the state untouched.

**Rename** — clicking the pencil swaps the alias span for an `<input>` pre-filled with the current alias (or empty if `alias === null`). Pressing Enter or blurring submits; pressing Escape cancels. Submission calls `PATCH /api/datasets/{id}` with `{alias: trimmed}`. On `r.ok`, patches the row's alias in agent state. On 4xx, shows the error message inline below the row (a small red `<span>`); on 5xx, logs and keeps the input open.

The input enforces the same rules as the route (non-empty, no whitespace, ≤ 64 chars), with a `pattern` attribute and `maxLength` to fail fast. Submission with an unchanged alias is treated as cancel (no request).

### 4.5 Lineage indication

Under each row whose `parent_ids` is non-empty, a small italic line:

```
  ← {parent_alias_or_id}, {parent_alias_or_id}
```

The frontend resolves each parent id against the current `datasets[]` list to display its alias if present, otherwise the id. Parents that have been deleted (orphans) fall back to the bare id with a strikethrough.

This adds one read of the datasets list per render, O(n²) in the worst case (n parents × n datasets). At expected n ≤ 20 this is fine; a `Map` lookup is unnecessary.

### 4.6 `DatasetMetaLite.parent_ids`

To render lineage without an extra fetch, `DatasetMetaLite` is extended with `parent_ids: list[str]` (default empty):

- `backend/geo_agent/models.py` — add the field.
- Every tool that constructs a `DatasetMetaLite` from a full `DatasetMeta` passes `parent_ids=meta.lineage.parent_ids`. Sites: `select_features.py`, `filter_attributes.py`, `aggregate.py` (only when it returns a Command), `spatial_overlay.py`, `spatial_join.py`, `transform_geometry.py`, `routes/datasets.py::create_drawing`.
- `backend/geo_agent/agent/prompt_builder.format_datasets_summary` does **not** include `parent_ids` in the prompt — the per-turn summary stays compact, and the agent has `describe_dataset` for the full picture.
- `frontend/lib/types.ts` — add `parent_ids: z.array(z.string()).default([])`.
- `frontend/components/GeoPage.tsx` hydration mapping — pass `parent_ids: m.lineage?.parent_ids ?? []`.

This is the only change that touches every dataset-producing tool. It is mechanical (one constructor argument per call site) and covered by the unit tests that already assert each tool's returned meta.

## 5. Edge cases

- **`active_layers` referencing a deleted dataset.** `delete_dataset` strips the id from `active_layers`. The frontend's `DatasetLayer` component is keyed by id; once the agent state update lands, the now-orphan layer unmounts cleanly.
- **`active_layers` after `clear_all_datasets`.** Same — the tool zeroes the list.
- **Alias collision on rename when the *same* dataset is being renamed to its own alias.** Treated as a no-op (no `alias_conflict` error). The validator computes "another dataset already uses this alias" by checking `m.alias == new_alias and m.id != rid`.
- **Frontend hydration race.** `GeoPage.tsx` fetches `/api/datasets` on mount and pushes the rows into agent state through `setAgentState`. After `DELETE /datasets` + reload, the fetch returns `[]`, the push is a no-op, and the agent starts with the empty `EMPTY_STATE`. No additional sync needed.
- **`DELETE /datasets` during an agent run.** Not possible in normal use — the user opens the chat panel header to click the button, and the page reloads immediately after. We do not need an "in-flight cancel" path for the POC.

## 6. Tests

### 6.1 Unit tests (one file per tool, mirroring existing layout)

- `backend/tests/unit/test_tool_delete_dataset.py`
  - happy path: create two datasets, delete one by id, assert the other survives and the deleted one raises `FileNotFoundError`;
  - by alias: same but via alias;
  - removes from `active_layers`: starting state has the id in `active_layers`, after the tool the returned `Command` clears it;
  - missing dataset → `dataset_not_found` error with the correct suggestion.
- `backend/tests/unit/test_tool_rename_dataset.py`
  - happy path: rename `result_001` from `null` alias to `"zone_park"`, assert `store.get_meta` returns the new alias;
  - invalid alias (empty, whitespace, too long) → `bad_input`;
  - duplicate alias → `alias_conflict`;
  - missing dataset → `dataset_not_found`;
  - same-id same-alias (no-op) → no error.
- `backend/tests/unit/test_tool_clear_all_datasets.py`
  - happy path with three datasets: returns `{"deleted": 3}`, `Command` zeroes both `datasets` and `active_layers`, `store.list()` is empty;
  - empty store → `{"deleted": 0}`, no error.

These tests follow the `tmp_path` + `FileSystemResultStore` + `init_services` pattern used by `test_tool_filter_attributes.py` etc.

### 6.2 Integration tests

`backend/tests/integration/test_datasets_route.py` (extend existing file):

- `DELETE /datasets` with two datasets returns `{"deleted": 2}` and a subsequent `GET /datasets` returns `[]`.
- `DELETE /datasets` on empty store returns `{"deleted": 0}`.
- `DELETE /datasets/{id}` happy path; non-existent id → 404.
- `PATCH /datasets/{id}` happy path; invalid alias → 400; collision → 409; non-existent id → 404.

### 6.3 Frontend

- Extend `frontend/tests/unit/DatasetPanel.test.tsx` (new file if it doesn't exist) for:
  - rendering groups with mixed-operation input (zones / WFS / derived sections appear with correct counts);
  - inline-rename happy path: pencil click → input → Enter → `PATCH` called → row alias updates (mock `fetch`);
  - rename validation (whitespace input) is rejected client-side before any `fetch`;
  - delete-row triggers `confirm` (mocked to true), calls `DELETE`, removes the row from rendered output;
  - lineage line shows parent alias when present, falls back to id when the parent is gone.
- The "Tout effacer" / "Nouvelle conversation" reload flows stay manually verified — `window.location.reload()` and `window.confirm` are awkward to assert in Vitest, and the underlying `DELETE /datasets` is already covered by the integration test.

## 7. Out of scope

- **Cascade delete of derived datasets.** Deleting `result_001` when `result_005` lists it in `lineage.parent_ids` leaves `result_005` with a dangling reference, surfaced in the UI as a struck-through parent id (see 4.5). Acceptable for the POC.
- **Soft delete / undo.** No "Recently deleted" tray.
- **Per-session isolation.** The store still has no session id. `clear_all_datasets` and `DELETE /datasets` operate on the entire store — fine for single-user POC, would need rework for multi-tenant.
- **A `confirm` dialog for the agent's `clear_all_datasets`.** The prompt guard is the safety net; an in-band confirmation would require a separate skill on the agent side and is not worth it for this scope.
- **Drag-and-drop reordering of datasets.** Groups are ordered by id ascending and not user-rearrangeable.
- **Multi-select delete from the panel.** Only per-row delete or clear-all.
- **Visualizing the full lineage tree** (a graph view, indented hierarchy, etc.). Only the immediate parents are shown.

## 8. Risks

- **Gemma local ignores the prompt guard and calls `clear_all_datasets` anyway.** Mitigation: the guard is short and in the same prose voice as the rest of the prompt; if it leaks, the worst case is the user reloses datasets that were one chat turn old. Documented; revisit only if observed in practice.
- **Confirm dialog dismissed by accident.** The dialog returns `false`, the function returns early, neither the thread nor the datasets reset. User clicks again to retry. Low risk.
- **`DatasetMetaLite.parent_ids` extension breaks something subtle.** Every dataset-producing tool constructs the type explicitly, and the tests already assert each tool's returned meta. The risk is omitting a constructor argument — easy to catch with the existing unit tests. Lite is a Pydantic model with a default factory, so old code paths that skip the field still work, but new code paths must pass it for lineage to render.
- **Inline-rename races with an agent turn that touches the same dataset.** The frontend's `PATCH` and the agent's `rename_dataset` tool write through the same store. If both fire within the same tick, the last writer wins. The window is small (one network round-trip), and the user-visible outcome is "the alias I just typed got overwritten" — a minor annoyance, not data loss. Not worth a lock.
