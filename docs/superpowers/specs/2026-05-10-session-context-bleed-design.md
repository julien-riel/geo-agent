# Session Context Bleed — Design Spec

**Date:** 2026-05-10
**Status:** Approved (pending user spec review)
**Branch target:** `feature/drawing-as-dataset` (or a follow-up branch off `main` after this branch merges)

## Problem

After the drawing-as-dataset work, the happy-path is functional but two issues remain:

1. **Stale chat history across reloads.** CopilotKit/LangGraph join the same thread on every page load (no thread management on the frontend), so the `MemorySaver` checkpointer keeps prior conversations. Old `zone_N` references from past sessions bleed into new requests.
2. **The LLM never sees `state.datasets`.** `create_react_agent` in `graph.py` is wired with a static `prompt=SYSTEM_PROMPT`. The TypedDict state propagates through AGUI but the LLM only ever sees `state["messages"]` — so the agent has to discover datasets via tool calls. Combined with #1, this leads to the agent using stale aliases or asking the user to redraw.

Symptoms observed during manual e2e:
- After drawing `zone_8`, the agent referenced `zone_7` (from a previous chat) when answering "Trouve les chaussées dans cette zone".
- Even with a prompt directive saying "FIRST tool call MUST be `list_datasets`", the small LLM (`qwen2.5:7b`) ignored it and proceeded with stale assumptions.

## Goals

- A page reload in the same browser tab keeps the current conversation intact (good UX during refresh).
- A new tab — or coming back the next day after the tab was closed — starts a fresh conversation.
- A "Nouvelle conversation" button in the chat sidebar header lets the user reset on demand.
- The agent always sees the current datasets in its LLM context, regardless of chat history, so it can ground references like "cette zone" without depending on tool-call discipline.

## Non-goals

- Long-term persistence (à la ChatGPT history).
- Garbage collection of result-store files when a session is abandoned.
- Multi-conversation history UI (one chat at a time is fine).
- Backend session management beyond the existing `MemorySaver` (which lives in process memory; restart wipes it — that's acceptable).

## Architecture

Three independent blocks. They can be reviewed and implemented in any order, but ship together.

### Block 1 — Tab-scoped thread id (frontend)

The frontend generates a UUIDv4 on first load, stores it in `sessionStorage` under the key `geo-agent-thread-id`, and passes it to `useCoAgent` so AGUI/CopilotKit pin the LangGraph thread to that id.

**Why `sessionStorage` (not `localStorage`)?** It survives reloads in the same tab but not across tabs and not after tab close. Matches the requirement exactly.

**Backend impact:** none. LangGraph's `MemorySaver` creates an empty checkpoint for any unknown thread id, so a fresh UUID just works.

**Surface:**
- New helper module `frontend/lib/threadId.ts` exposes:
  ```ts
  function getOrCreateThreadId(): string  // returns existing or generates+stores new
  function resetThreadId(): string         // generates a new UUID, overwrites storage, returns it
  ```
- `GeoPage.tsx` calls `getOrCreateThreadId()` once on mount and passes the value to `useCoAgent({ threadId })` (or whatever the CopilotKit prop is called — confirm during implementation).

### Block 2 — State grounding via dynamic prompt (backend)

`create_react_agent` accepts either a static prompt string OR a callable that takes the agent state and returns the message list. We switch to a callable so the system prompt is regenerated on every LLM turn, embedding a compact summary of the current datasets.

**Format appended to the existing `SYSTEM_PROMPT`:**

```
---
Current datasets in this session:
- result_001 (alias=zone_1, operation=user_drawing, 1 features, bbox=[-73.6, 45.5, -73.55, 45.55])
- result_002 (alias=parcs_in_zone, operation=select_features, 47 features, bbox=[-73.6, 45.5, -73.55, 45.55])
```

When `state["datasets"]` is empty or missing: `Current datasets in this session: (none)`. List ALL datasets, not a truncated subset — user explicitly chose full listing during brainstorming. (We can add truncation later if token usage becomes a real problem.)

**Implementation:**
- New module `backend/geo_agent/agent/prompt_builder.py` exposes `build_prompt(state) -> list[BaseMessage]` and `format_datasets_summary(datasets) -> str`. Keeping the formatter in its own module makes it independently testable.
  ```python
  def build_prompt(state: AgentState) -> list[BaseMessage]:
      summary = format_datasets_summary(state.get("datasets") or [])
      sys_text = f"{SYSTEM_PROMPT}\n---\n{summary}"
      return [SystemMessage(sys_text), *state["messages"]]
  ```
- `format_datasets_summary` produces the bullet list (or `(none)`).
- `build_agent` is updated to pass `prompt=build_prompt`.

**Why this works:**
- The LLM sees the dataset summary every turn, no chat-history dependency.
- Recomputed each turn, so additions/deletions are reflected immediately.
- No accumulation: only the latest summary is in context (the previous one is reconstructed from state, not appended again).

### Block 3 — "Nouvelle conversation" button (frontend)

A button in the `CopilotSidebar` header that:
1. Calls `resetThreadId()` to mint a new UUID and overwrite `sessionStorage`.
2. Clears local agent state: `setState({ datasets: [], active_layers: [], last_error: null })`.
3. Triggers a re-mount of the CopilotSidebar so the chat UI clears (mechanism: bump a `key` prop with the new threadId, or whatever React-friendly remount the CopilotKit API supports).

**UI placement:** in the chat sidebar header strip, alongside Help/Debug/Close.

**Layout (textual):**
```
[Help] [Debug] [↻ Nouveau] [×]
```

The button label is "Nouveau" (short for "Nouvelle conversation" — the icon ↻ + the word disambiguates). Tooltip: "Démarrer une nouvelle conversation".

**Mechanism:** `CopilotSidebar` accepts custom header / button slots. The implementation plan must verify the exact prop name in `@copilotkit/react-ui` (likely `Header`, `headerActions`, or similar) and inject the button there. If no slot exists, fall back to placing the button in the sidebar via the `instructions`/`labels` mechanism, OR (last resort) place it in the existing `DatasetPanel` instead — but that needs user re-approval.

## Data Flow

### Normal flow (with the changes)
1. User opens app → `getOrCreateThreadId()` returns existing or fresh UUID, persisted in `sessionStorage`.
2. `useCoAgent` is initialized with `threadId=<uuid>` and `initialState={datasets:[], active_layers:[], last_error:null}`.
3. User draws polygon → `POST /api/datasets/drawing` → response appended to `state.datasets`, id appended to `state.active_layers`.
4. User asks "Trouve les chaussées dans cette zone" → AGUI sends message + state to backend with the same `threadId`.
5. Backend `build_prompt(state)` includes the current `datasets` summary. The LLM sees the system prompt + dataset list + user message and picks `zone_N` correctly.
6. Agent calls `select_features(geometry_source={"type":"dataset","dataset_id":"result_NNN","use_geometry":true})` (using the resolved id from the summary).
7. New result dataset is created, AGUI streams the `state.datasets` update back, frontend appends, dataset card appears.

### Reset flow
1. User clicks "Nouveau" → `resetThreadId()` mints new UUID, writes to `sessionStorage`.
2. Local state cleared via `setState`.
3. `CopilotSidebar` remounts (key change with the new threadId).
4. Next message creates a fresh checkpoint on the backend under the new thread id.

### Reload flow
1. Page reload → `getOrCreateThreadId()` reads existing thread id from `sessionStorage`.
2. `useCoAgent` rejoins the same backend thread → conversation continues.
3. **Caveat:** local frontend state (`datasets`, `active_layers`) is wiped because we don't persist it. AGUI's first state-sync from backend will be empty (the checkpointer doesn't store `datasets` since the agent doesn't write it). So the dataset panel goes blank on reload but the conversation messages persist.
   - This is acceptable for the iteration: the user can redraw zones if needed; chat memory is preserved.
   - If this turns out to be annoying in practice, we'd add a "rehydrate datasets from disk" call (e.g. fetch `/datasets`) — out of scope for this spec.

### New tab flow
1. New tab → `sessionStorage` is empty for that origin in this tab → fresh UUID generated.
2. Backend creates a new thread → empty checkpoint → fresh conversation.

## Components

| File | Type | Responsibility |
|---|---|---|
| `frontend/lib/threadId.ts` | new | UUID generation, sessionStorage I/O. Pure functions. |
| `frontend/components/GeoPage.tsx` | modify | Wire `threadId` into `useCoAgent`; render the reset button; handle the reset callback. |
| `frontend/components/NewConversationButton.tsx` | new (small) | Encapsulates the button UI + click handler. Receives `onReset` prop. |
| `backend/geo_agent/agent/graph.py` | modify | Replace `prompt=SYSTEM_PROMPT` with `prompt=build_prompt`. |
| `backend/geo_agent/agent/prompt_builder.py` | new | `build_prompt(state)`, `format_datasets_summary(datasets)`. |
| `backend/tests/unit/test_prompt_builder.py` | new | Tests for `format_datasets_summary` (empty list, multiple datasets) and that `build_prompt` returns expected message shape. |

## Error Handling

- **`sessionStorage` unavailable** (private browsing in some browsers, restrictive permissions): `getOrCreateThreadId` falls back to an in-memory module-level variable so the session lasts as long as the page is loaded but no longer survives reloads. We `console.warn` once but don't fail the app.
- **Malformed thread id in storage** (e.g. user manually edited it): if not a valid UUID, treat as missing and generate a new one.
- **Backend `build_prompt` receives malformed `state["datasets"]`** (any item missing required fields): the formatter shows `(unknown dataset)` for that entry rather than crashing. The LLM still sees the rest.
- **CopilotKit doesn't expose a `threadId` prop or header slot**: implementation plan must surface this BEFORE writing code; possible fallbacks are documented in Block 1/3.

## Testing

### Unit tests (backend)
- `format_datasets_summary([])` returns `"Current datasets in this session: (none)"`.
- `format_datasets_summary([m1, m2])` returns a bulleted list with id, alias, operation, feature_count, bbox for each.
- `format_datasets_summary` tolerates a dict missing the `alias` field (returns `alias=None` or omits gracefully).
- `build_prompt({"datasets":[m1], "messages":[...], "active_layers":[], "last_error":None})` returns a list whose first message is `SystemMessage` containing the summary, followed by the existing messages in order.
- `build_agent(settings)` doesn't raise (smoke).

### Unit tests (frontend, Vitest)
- `getOrCreateThreadId()` returns the same value on repeated calls within the same session.
- `getOrCreateThreadId()` returns a different value if `sessionStorage` is cleared between calls.
- `resetThreadId()` mints a UUID different from the previous one and overwrites storage.
- All three handle `sessionStorage` throwing (mocked) without crashing.

### E2E (Playwright)
- Existing smoke test: still passes (draw → dataset card visible & checked).
- New smoke test: click "Nouveau" → assert chat history is empty AND dataset list is empty. (Use a stubbed POST again for isolation.)

### Manual happy-path
After implementation:
1. Open app, draw a zone, ask "Trouve les chaussées dans cette zone".
2. Confirm: agent picks the latest user_drawing (no stale alias), announces it ("J'utilise zone_X..."), result dataset appears with non-zero feature_count, and `show_on_map` is called.
3. Click "Nouveau" → both panels empty, fresh chat.
4. Reload page in same tab → conversation persists.
5. Open a new tab to the same URL → conversation is fresh.

## Open Questions Resolved During Brainstorm

- ✅ Reload behavior: tab-scoped (sessionStorage), not localStorage, not in-memory-only.
- ✅ Reset button: yes, in the chat sidebar header.
- ✅ State grounding: yes, full dataset list (no truncation), recomputed every turn via `prompt` callable.
- ✅ Format: bullet list with id, alias, operation, feature_count, bbox.

## Out of Scope (explicit, for clarity)

- Persisting `state.datasets` across reloads (today datasets re-appear only via redraw or chat replay).
- Multiple parallel conversations.
- A "thread history" UI showing past conversations.
- Backend persistence of checkpoints across uvicorn restarts.
- Truncating the dataset summary if it grows too large — flagged for future consideration if token usage becomes a problem.
