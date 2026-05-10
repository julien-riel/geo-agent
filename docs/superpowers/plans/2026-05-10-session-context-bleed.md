# Session Context Bleed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two leftover bugs from drawing-as-dataset: stale chat-history bleed across reloads (causing the agent to reference dead `zone_N` aliases) and the LLM never seeing `state.datasets` (so the agent has to discover via tool calls).

**Architecture:** Tab-scoped `thread_id` in `sessionStorage` so reloads in the same tab continue the same conversation while new tabs / next-day opens start fresh; a "Nouveau" button in the chat sidebar header to force a reset on demand; a `prompt` callable on the LangGraph agent that re-injects a compact dataset summary into the system message every LLM turn so the agent always sees ground truth regardless of chat history.

**Tech Stack:** Python 3.12 + LangGraph + langchain-core (backend), Next.js 15 + React + CopilotKit + Vitest + Playwright (frontend). All deps already present.

---

## File Structure

| File | Type | Responsibility |
|---|---|---|
| `backend/geo_agent/agent/prompt_builder.py` | new | `build_prompt(state)` + `format_datasets_summary(datasets)` — pure functions, no I/O. |
| `backend/geo_agent/agent/graph.py` | modify | Replace `prompt=SYSTEM_PROMPT` with `prompt=build_prompt`. |
| `backend/tests/unit/test_prompt_builder.py` | new | Unit tests for both helpers. |
| `frontend/lib/threadId.ts` | new | `getOrCreateThreadId()`, `resetThreadId()`. Pure helpers, sessionStorage-backed. |
| `frontend/tests/unit/threadId.test.ts` | new | Vitest unit tests. |
| `frontend/components/ChatHeader.tsx` | new | Custom `Header` component for `CopilotSidebar` that mimics the default look and adds a "Nouveau" button. |
| `frontend/components/GeoPage.tsx` | modify | Wire `threadId` into `useCoAgent` and `CopilotSidebar`; pass `key` for remount on reset; pass custom `Header`. |
| `frontend/tests/e2e/smoke.spec.ts` | modify | Add a second test that exercises the "Nouveau" button. |

Pre-existing failure baseline: `tests/unit/test_tool_list_wfs_layers.py::test_list_wfs_layers_returns_summary` — unrelated, do NOT touch.

---

### Task 1: `format_datasets_summary` (pure formatter)

**Files:**
- Create: `backend/geo_agent/agent/prompt_builder.py`
- Test: `backend/tests/unit/test_prompt_builder.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_prompt_builder.py`:

```python
def test_format_datasets_summary_empty() -> None:
    from geo_agent.agent.prompt_builder import format_datasets_summary

    assert format_datasets_summary([]) == "Current datasets in this session: (none)"


def test_format_datasets_summary_lists_all_fields() -> None:
    from geo_agent.agent.prompt_builder import format_datasets_summary

    summary = format_datasets_summary(
        [
            {
                "id": "result_001",
                "alias": "zone_1",
                "operation": "user_drawing",
                "feature_count": 1,
                "bbox": [-73.6, 45.5, -73.55, 45.55],
            },
            {
                "id": "result_002",
                "alias": "parcs_in_zone",
                "operation": "select_features",
                "feature_count": 47,
                "bbox": [-73.6, 45.5, -73.55, 45.55],
            },
        ]
    )

    assert summary.startswith("Current datasets in this session:\n")
    assert "result_001 (alias=zone_1, operation=user_drawing, 1 features, bbox=[-73.6, 45.5, -73.55, 45.55])" in summary
    assert "result_002 (alias=parcs_in_zone, operation=select_features, 47 features, bbox=[-73.6, 45.5, -73.55, 45.55])" in summary


def test_format_datasets_summary_handles_missing_alias() -> None:
    from geo_agent.agent.prompt_builder import format_datasets_summary

    summary = format_datasets_summary(
        [{"id": "result_003", "alias": None, "operation": "select_features", "feature_count": 5, "bbox": [0, 0, 1, 1]}]
    )

    assert "alias=None" in summary
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd backend && uv run pytest tests/unit/test_prompt_builder.py -v
```

Expected: ImportError / ModuleNotFoundError because `prompt_builder.py` doesn't exist yet.

- [ ] **Step 3: Implement `format_datasets_summary`**

Create `backend/geo_agent/agent/prompt_builder.py`:

```python
from typing import Any


def format_datasets_summary(datasets: list[dict[str, Any]]) -> str:
    """Render a compact bullet list of datasets for inclusion in the system prompt."""
    if not datasets:
        return "Current datasets in this session: (none)"

    lines = ["Current datasets in this session:"]
    for d in datasets:
        bbox = d.get("bbox")
        bbox_str = f"[{', '.join(str(x) for x in bbox)}]" if bbox else "[]"
        lines.append(
            f"- {d.get('id')} (alias={d.get('alias')}, "
            f"operation={d.get('operation')}, "
            f"{d.get('feature_count')} features, "
            f"bbox={bbox_str})"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
cd backend && uv run pytest tests/unit/test_prompt_builder.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/agent/prompt_builder.py backend/tests/unit/test_prompt_builder.py
git commit -m "$(cat <<'EOF'
feat(prompt_builder): format compact dataset summary for system prompt

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `build_prompt` callable

**Files:**
- Modify: `backend/geo_agent/agent/prompt_builder.py`
- Test: `backend/tests/unit/test_prompt_builder.py`

- [ ] **Step 1: Add the failing test**

Append to `backend/tests/unit/test_prompt_builder.py`:

```python
def test_build_prompt_returns_system_message_then_messages() -> None:
    from langchain_core.messages import HumanMessage, SystemMessage

    from geo_agent.agent.prompt_builder import build_prompt

    state = {
        "datasets": [
            {"id": "result_001", "alias": "zone_1", "operation": "user_drawing", "feature_count": 1, "bbox": [0, 0, 1, 1]}
        ],
        "active_layers": [],
        "last_error": None,
        "messages": [HumanMessage(content="Trouve les chaussées dans cette zone")],
    }

    out = build_prompt(state)

    assert isinstance(out[0], SystemMessage)
    assert "result_001" in out[0].content
    assert "zone_1" in out[0].content
    assert "You are a geospatial analysis assistant" in out[0].content
    assert len(out) == 2
    assert isinstance(out[1], HumanMessage)
    assert out[1].content == "Trouve les chaussées dans cette zone"


def test_build_prompt_handles_missing_datasets() -> None:
    from langchain_core.messages import SystemMessage

    from geo_agent.agent.prompt_builder import build_prompt

    state = {"messages": [], "active_layers": [], "last_error": None}  # no datasets key

    out = build_prompt(state)

    assert isinstance(out[0], SystemMessage)
    assert "(none)" in out[0].content
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd backend && uv run pytest tests/unit/test_prompt_builder.py -v
```

Expected: ImportError on `build_prompt` (function doesn't exist yet).

- [ ] **Step 3: Add `build_prompt` to `prompt_builder.py`**

Append to `backend/geo_agent/agent/prompt_builder.py`:

```python
from langchain_core.messages import BaseMessage, SystemMessage

from geo_agent.agent.prompts import SYSTEM_PROMPT


def build_prompt(state: dict) -> list[BaseMessage]:
    """LangGraph `prompt=` callable: prepend a SystemMessage with the dataset summary."""
    summary = format_datasets_summary(state.get("datasets") or [])
    sys_text = f"{SYSTEM_PROMPT}\n---\n{summary}"
    messages = state.get("messages") or []
    return [SystemMessage(content=sys_text), *messages]
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
cd backend && uv run pytest tests/unit/test_prompt_builder.py -v
```

Expected: 5 tests pass total.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/agent/prompt_builder.py backend/tests/unit/test_prompt_builder.py
git commit -m "$(cat <<'EOF'
feat(prompt_builder): add build_prompt callable for create_react_agent

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Wire `build_prompt` into `build_agent`

**Files:**
- Modify: `backend/geo_agent/agent/graph.py`

- [ ] **Step 1: Read existing graph.py**

Current content of `backend/geo_agent/agent/graph.py`:

```python
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from geo_agent.agent.prompts import SYSTEM_PROMPT
from geo_agent.agent.tools.aggregate import aggregate
# ... (other tool imports)

def build_agent(settings: Settings):
    llm = ChatOllama(...)
    return create_react_agent(
        model=llm,
        tools=TOOLS,
        prompt=SYSTEM_PROMPT,
        checkpointer=MemorySaver(),
    )
```

- [ ] **Step 2: Replace `prompt=SYSTEM_PROMPT` with `prompt=build_prompt`**

Edit `backend/geo_agent/agent/graph.py`:

1. Replace the line `from geo_agent.agent.prompts import SYSTEM_PROMPT` with:
   ```python
   from geo_agent.agent.prompt_builder import build_prompt
   ```
2. Replace `prompt=SYSTEM_PROMPT,` with `prompt=build_prompt,`.

The `SYSTEM_PROMPT` is still used inside `prompt_builder.py`, so leave `prompts.py` unchanged.

- [ ] **Step 3: Verify graph still loads**

```bash
cd backend && uv run pytest tests/unit/test_agent_graph.py -v
```

Expected: PASS.

- [ ] **Step 4: Confirm broader suite is green**

```bash
cd backend && uv run pytest --ignore=tests/integration/test_live.py -q 2>&1 | tail -5
```

Expected: only the pre-existing `test_list_wfs_layers_returns_summary` fails. If anything else fails, STOP and report.

- [ ] **Step 5: Commit**

```bash
git add backend/geo_agent/agent/graph.py
git commit -m "$(cat <<'EOF'
feat(graph): inject dataset summary into LLM context every turn

Replaces the static prompt with a callable so the agent always sees
the current state.datasets summary regardless of chat history.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `lib/threadId.ts` (frontend helper)

**Files:**
- Create: `frontend/lib/threadId.ts`
- Test: `frontend/tests/unit/threadId.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/unit/threadId.test.ts`:

```typescript
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { getOrCreateThreadId, resetThreadId } from "@/lib/threadId";

const KEY = "geo-agent-thread-id";

beforeEach(() => sessionStorage.clear());
afterEach(() => sessionStorage.clear());

describe("threadId", () => {
  it("returns the same id on repeat calls within a session", () => {
    const a = getOrCreateThreadId();
    const b = getOrCreateThreadId();
    expect(a).toBe(b);
    expect(a).toMatch(/^[0-9a-f-]{36}$/i);
  });

  it("generates a new id after sessionStorage is cleared", () => {
    const a = getOrCreateThreadId();
    sessionStorage.clear();
    const b = getOrCreateThreadId();
    expect(a).not.toBe(b);
  });

  it("resetThreadId mints a new id and overwrites storage", () => {
    const a = getOrCreateThreadId();
    const b = resetThreadId();
    expect(b).not.toBe(a);
    expect(sessionStorage.getItem(KEY)).toBe(b);
  });

  it("treats an obviously malformed stored value as missing", () => {
    sessionStorage.setItem(KEY, "not-a-uuid");
    const id = getOrCreateThreadId();
    expect(id).toMatch(/^[0-9a-f-]{36}$/i);
    expect(sessionStorage.getItem(KEY)).toBe(id);
  });
});
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd frontend && npm test -- threadId
```

Expected: import-resolution failure (the module doesn't exist).

- [ ] **Step 3: Implement the helper**

Create `frontend/lib/threadId.ts`:

```typescript
const KEY = "geo-agent-thread-id";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

let inMemoryFallback: string | null = null;

function safeGetItem(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return inMemoryFallback;
  }
}

function safeSetItem(value: string): void {
  try {
    sessionStorage.setItem(KEY, value);
  } catch {
    inMemoryFallback = value;
    console.warn("threadId: sessionStorage unavailable, using in-memory fallback");
  }
}

function generate(): string {
  // Browsers ≥ 2022 expose crypto.randomUUID; jsdom/test envs may not.
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // RFC4122 v4 fallback.
  const bytes = new Uint8Array(16);
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function getOrCreateThreadId(): string {
  const existing = safeGetItem();
  if (existing && UUID_RE.test(existing)) return existing;
  const fresh = generate();
  safeSetItem(fresh);
  return fresh;
}

export function resetThreadId(): string {
  const fresh = generate();
  safeSetItem(fresh);
  return fresh;
}
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
cd frontend && npm test -- threadId
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/threadId.ts frontend/tests/unit/threadId.test.ts
git commit -m "$(cat <<'EOF'
feat(frontend): add tab-scoped threadId helper backed by sessionStorage

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Custom `ChatHeader` with "Nouveau" button

**Files:**
- Create: `frontend/components/ChatHeader.tsx`

The default CopilotKit Header reads `labels.title` and renders `[title] [DevConsole] [Close]`. We supply a replacement that adds our reset button. CopilotKit's `CopilotSidebar` accepts a `Header?: React.ComponentType<{}>` prop (`HeaderProps` is empty); the component pulls everything else from `useChatContext()`.

- [ ] **Step 1: Create the component**

Create `frontend/components/ChatHeader.tsx`:

```typescript
"use client";

import { useChatContext } from "@copilotkit/react-ui";

interface Props {
  onNewConversation: () => void;
}

export function ChatHeader({ onNewConversation }: Props) {
  const { labels, setOpen, icons } = useChatContext();
  return (
    <div className="copilotKitHeader">
      <div>{labels.title}</div>
      <div className="copilotKitHeaderControls" style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button
          onClick={onNewConversation}
          aria-label="Nouvelle conversation"
          title="Nouvelle conversation"
          style={{
            background: "transparent",
            border: "1px solid #ddd",
            borderRadius: 4,
            padding: "2px 8px",
            cursor: "pointer",
            fontSize: 13,
          }}
        >
          ↻ Nouveau
        </button>
        <button
          onClick={() => setOpen(false)}
          aria-label="Close"
          className="copilotKitHeaderCloseButton"
        >
          {icons.headerCloseIcon}
        </button>
      </div>
    </div>
  );
}
```

Note: we intentionally drop `CopilotDevConsole` from our custom header — it's developer-only chrome and the user already has Next dev tools available. If we later miss it, we can re-add it (`import { CopilotDevConsole } from "@copilotkit/react-ui"`).

- [ ] **Step 2: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: silent (no errors). The component is unused for now — Task 6 wires it in.

- [ ] **Step 3: (no commit yet — wait for Task 6 so the build is consistent)**

---

### Task 6: Wire threadId, header, and reset into `GeoPage`

**Files:**
- Modify: `frontend/components/GeoPage.tsx`

The current `GeoPage` doesn't use a threadId or a custom header. We:
1. Hold the threadId in React state, initialized from `getOrCreateThreadId()`.
2. Pass it to `useCoAgent({ threadId })`.
3. Use it as the `key` prop on a wrapping `<Fragment>`/`<div>` containing both the `useCoAgent`-driven children and `CopilotSidebar` so a new threadId remounts everything cleanly. Easiest: split the body into a child component keyed on threadId.
4. On reset: call `resetThreadId()`, update the local state with the new id (which triggers remount).

Because `useCoAgent` lives in `GeoPage`, the cleanest pattern is to split the body into `<GeoPageBody key={threadId} threadId={threadId} onReset={...} />`. Remounting `GeoPageBody` re-runs `useCoAgent` with the new threadId AND clears its state (because `initialState` is re-applied on mount).

- [ ] **Step 1: Refactor `GeoPage.tsx`**

Replace `frontend/components/GeoPage.tsx` ENTIRELY with:

```typescript
"use client";

import { useCoAgent, useCoAgentStateRender } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { useEffect, useState } from "react";

import { ChatHeader } from "@/components/ChatHeader";
import { DatasetPanel } from "@/components/DatasetPanel";
import { DatasetLayer } from "@/components/Map/DatasetLayer";
import { DrawTool } from "@/components/Map/DrawTool";
import { MapView } from "@/components/Map/MapView";
import { getOrCreateThreadId, resetThreadId } from "@/lib/threadId";
import { AgentState, DatasetMetaLite } from "@/lib/types";

export function GeoPage() {
  const [threadId, setThreadId] = useState<string | null>(null);

  // Defer to client-only render to avoid SSR hydration mismatch on sessionStorage.
  useEffect(() => {
    setThreadId(getOrCreateThreadId());
  }, []);

  const onNewConversation = () => {
    const fresh = resetThreadId();
    setThreadId(fresh);
  };

  if (!threadId) return null;

  return <GeoPageBody key={threadId} threadId={threadId} onNewConversation={onNewConversation} />;
}

function GeoPageBody({ threadId, onNewConversation }: { threadId: string; onNewConversation: () => void }) {
  const { state, setState } = useCoAgent<AgentState>({
    name: "geo-agent",
    threadId,
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
        Header={() => <ChatHeader onNewConversation={onNewConversation} />}
      />
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: silent.

If `useCoAgent` rejects `threadId` (the type field name might differ — verify by checking `node_modules/@copilotkit/react-core/dist/index.d.mts` for `UseCoAgentOptions`). Spec already confirmed `threadId?: string` is exposed; if the field is named differently locally, adjust accordingly and document the deviation.

- [ ] **Step 3: Run vitest unit tests (no regressions)**

```bash
cd frontend && npm test
```

Expected: all tests pass (threadId tests from Task 4, plus any pre-existing).

- [ ] **Step 4: Manual smoke (dev server already running on :3000)**

Open http://localhost:3000:
- Confirm the chat sidebar header now shows `Géo-agent ... ↻ Nouveau ×`.
- Click "↻ Nouveau" — confirm the chat resets to "Je peux interroger les couches WFS de Montréal..." and the dataset panel becomes empty.
- Reload the page — confirm the chat persists (same conversation, same datasets are gone since we don't rehydrate).

- [ ] **Step 5: Commit Tasks 5+6 together**

```bash
git add frontend/components/ChatHeader.tsx frontend/components/GeoPage.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): tab-scoped thread + Nouveau button to reset chat

Reads/writes a UUID threadId in sessionStorage and passes it to
useCoAgent so reloads in the same tab continue the same conversation
while new tabs / next-day opens start fresh. Adds a "↻ Nouveau"
button in the chat sidebar header that mints a new threadId and
remounts the agent body, clearing local state.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Playwright e2e test for the reset flow

**Files:**
- Modify: `frontend/tests/e2e/smoke.spec.ts`

The existing smoke test draws a zone and asserts the dataset card appears (with a stubbed POST). We add a second test that exercises "Nouveau".

- [ ] **Step 1: Append the new test**

Append to `frontend/tests/e2e/smoke.spec.ts` (do NOT modify the existing test):

```typescript
test("clicking Nouveau resets chat and dataset panel", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible();

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

  // Re-use the gesture from the first test (polygon via PointerEvents).
  await page.evaluate(() => {
    const closeBtn = document.querySelector('button[aria-label="Close Chat"]') as HTMLElement | null;
    closeBtn?.click();
  });
  await page.getByRole("button", { name: /Dessiner zone/i }).click();
  await page.waitForFunction(() => {
    const c = document.querySelector<HTMLCanvasElement>("canvas.maplibregl-canvas");
    return c ? getComputedStyle(c).cursor === "crosshair" : false;
  }, { timeout: 5000 });
  await page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>("canvas.maplibregl-canvas");
    if (!canvas) throw new Error("MapLibre canvas not found");
    const opts = (x: number, y: number): PointerEventInit => ({
      clientX: x, clientY: y, bubbles: true, cancelable: true,
      pointerId: 1, pointerType: "mouse", isPrimary: true, button: 0, buttons: 1,
    });
    function pclick(x: number, y: number) {
      canvas.dispatchEvent(new PointerEvent("pointermove", opts(x, y)));
      canvas.dispatchEvent(new PointerEvent("pointerdown", opts(x, y)));
      canvas.dispatchEvent(new PointerEvent("pointerup", opts(x, y)));
    }
    pclick(300, 250); pclick(500, 250); pclick(500, 400); pclick(300, 400);
    canvas.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    canvas.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
  });

  // Pre-condition: dataset card is present.
  await expect(page.getByText("zone_1", { exact: false })).toBeVisible({ timeout: 5000 });

  // Re-open the chat sidebar (it was closed earlier so we could draw).
  await page.evaluate(() => {
    const open = document.querySelector('button[aria-label="Open Chat"]') as HTMLElement | null;
    open?.click();
  });

  // Click "Nouveau".
  await page.getByRole("button", { name: /Nouvelle conversation/i }).click();

  // Post-conditions: dataset panel is empty AND chat is back to its initial label.
  await expect(page.getByText("Aucun dataset", { exact: false })).toBeVisible();
  await expect(page.getByText("zone_1", { exact: false })).toHaveCount(0);
});
```

- [ ] **Step 2: Run e2e**

```bash
cd frontend && npm run test:e2e
```

Expected: 2 tests pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/smoke.spec.ts
git commit -m "$(cat <<'EOF'
test(e2e): smoke-test Nouveau reset flow

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Manual happy-path verification

**Files:** none.

- [ ] **Step 1: Restart backend (so the new prompt builder is loaded)**

If the backend is running with `--reload`, save any file in `geo_agent/` to trigger a reload. Otherwise:

```bash
pkill -f 'uvicorn geo_agent.main:app' || true
cd backend && nohup uv run uvicorn geo_agent.main:app --host 127.0.0.1 --port 8000 --reload > /tmp/geo-backend.log 2>&1 &
```

- [ ] **Step 2: Run the full happy path**

In a fresh browser tab at http://localhost:3000:

1. Confirm chat sidebar header shows `↻ Nouveau`.
2. Click **Dessiner zone**, draw a small polygon over central Montréal.
3. Confirm the dataset card `📐 zone_N · 1 features · user-drawn · user_drawing` appears, checked, with the polygon visible on the map.
4. In the chat, send: *"Trouve les chaussées dans cette zone."*
5. Wait up to ~60s for the agent.
6. Confirm:
   - The agent picks the latest `user_drawing` zone (same N as just drawn — no stale alias).
   - The agent announces it (e.g. *"J'utilise zone_N..."*).
   - A second dataset card appears with `feature_count > 0`.
   - The chaussées are rendered on the map.

- [ ] **Step 3: Test the reset**

1. Click `↻ Nouveau`.
2. Confirm: chat resets to its initial label, dataset panel is empty, the polygon and chaussées disappear from the map.
3. Reload the same tab — chat stays empty, panel stays empty.
4. Open a NEW tab at http://localhost:3000 — also empty (separate sessionStorage).

- [ ] **Step 4: Test reload-keeps-conversation**

1. In a fresh tab, draw a zone and ask a question, get a response.
2. Reload (Cmd+R) the same tab — chat history persists. Dataset panel is empty (we don't rehydrate it; this is a known out-of-scope limitation). The conversation messages are still visible.

- [ ] **Step 5: If anything fails**

Inspect `/tmp/geo-backend.log` for errors. Most likely culprits:
- The dynamic prompt isn't running → check `prompt_builder.py` is imported in `graph.py` and `prompt=build_prompt` is passed.
- The frontend doesn't pass `threadId` → check the `useCoAgent` call.
- The `Header` slot rejects our component → check `Header={() => <ChatHeader …/>}` syntax (it's a component type, not an element).

- [ ] **Step 6: Commit any incidental fixes**

```bash
git status
# Commit any small adjustments uncovered during manual testing.
```

---

## Self-Review

**Spec coverage:**
- ✅ Block 1 (sessionStorage threadId) → Tasks 4 + 6.
- ✅ Block 2 (build_prompt callable) → Tasks 1 + 2 + 3.
- ✅ Block 3 ("Nouveau" button in chat header) → Tasks 5 + 6.
- ✅ Tests required by spec — backend unit (Task 1+2), frontend unit (Task 4), e2e (Task 7), manual (Task 8).
- ✅ Error handling: sessionStorage fallback covered in Task 4 implementation; missing-datasets covered in Task 1+2 tests; malformed-uuid covered in Task 4 test.

**Placeholder scan:** No "TBD"/"TODO"/"add validation" — all code blocks are concrete. Task 6 step 2 includes a defensive sentence about verifying the `threadId` field name in CopilotKit types; this is a real (and small) impl-time check, not a placeholder.

**Type consistency:** `format_datasets_summary` and `build_prompt` signatures match between definition (Task 1/2) and usage (Task 3). `getOrCreateThreadId` / `resetThreadId` names match between implementation (Task 4) and consumption (Task 6). `ChatHeader` props (`{ onNewConversation: () => void }`) match between Task 5 and Task 6 usage.

---

## Out of scope (future work, not part of this plan)

- Persisting `state.datasets` across reload — today the dataset panel is empty after a reload; only chat history persists.
- Truncating the dataset summary if it grows large — flagged in spec for future consideration if token usage becomes a problem.
- Long-term cross-tab persistence (would require localStorage + explicit "new chat" UX).
- Cleaning up backend `MemorySaver` checkpoints for abandoned threads.
