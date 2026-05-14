# Charts on datasets — design

**Date:** 2026-05-14
**Scope:** Agent-rendered charts over dataset attributes (bar / pie / grouped bar) using ECharts.

## 1. Goal

Let the agent surface a visual summary of a dataset to the user inside the chat: frequency of an
attribute's values (bar or pie) and the result of an aggregation grouped by an attribute (grouped
bar). The user describes what they want in natural language; the agent picks the right tool and the
chart renders inline.

Out of scope for v1: histograms over numerical attributes, scatter/time-series, click-to-filter
interactivity, exporting charts.

## 2. Periphery decisions (locked in brainstorm)

| Decision | Choice |
|---|---|
| Trigger | Agent-only (LLM tool call). No user-driven chart button. |
| Chart types in v1 | bar (top values), pie/donut (top values), grouped bar (aggregation output) |
| Interactivity | Read-only. Default ECharts tooltip only. Filtering happens through the chat. |
| Widget shape | Card with header — same chrome as `MetadataWidget` and `SchemaWidget`. |
| Tool surface | Two narrow tools (Approach 2): `plot_attribute_distribution` and `plot_aggregation`. |

## 3. Architecture

```
┌─────────────── Backend ────────────────┐    ┌─────────── Frontend ────────────┐
│                                        │    │                                  │
│  geo_agent/services/chart_data.py      │    │  components/Widgets/             │
│    - top_values_for_chart(...)         │    │    ChartWidget.tsx               │
│    - aggregation_for_chart(...)        │    │      (ECharts wrapper)           │
│        → ChartData                     │    │                                  │
│                                        │    │  lib/echartsBuilders.ts          │
│  geo_agent/agent/tools/ui/             │    │    buildBarOption(data)          │
│    plot_attribute_distribution.py ─┐   │    │    buildPieOption(data)          │
│    plot_aggregation.py             │   │    │    buildGroupedBarOption(data)   │
│                                    │   │    │    buildOption(data) → dispatch  │
│  Both tools return ChartData       │   │    │                                  │
│  as the LLM-visible result.        ├───┼───►│  GeoPage.tsx                     │
│  Payload stays small (≤ 10 bins +  │   │    │    useCopilotAction(             │
│  counts, < 1 KB).                  │   │    │      "plot_attribute_..." /      │
│                                    │   │    │      "plot_aggregation",         │
│                                    │   │    │      render: <ChartWidget …/>)   │
└────────────────────────────────────┴───┘    └──────────────────────────────────┘
```

### 3.1 Boundaries

- **`services/chart_data.py`** — pure functions that compute a `ChartData` payload from a GeoJSON.
  No FastAPI route. Reusable from other places (a future REST endpoint, a non-agent UI).
- **`tools/ui/plot_*`** — thin LangGraph tools that resolve the dataset, call a service, and return
  the dict. Located alongside `inspect_dataset` because they render to the user but do not create a
  dataset.
- **`ChartWidget`** — single React component that dispatches on `chart_type`. Holds the ECharts
  lifecycle (`init` / `dispose` / resize).
- **`lib/echartsBuilders.ts`** — pure functions `data → ECharts option`. Testable without a DOM.

### 3.2 Data shape

The two tools return the same shape — a flat `ChartData`:

```ts
interface ChartData {
  chart_type: "bar" | "pie" | "grouped_bar";
  title: string;                                  // "Fréquence — type_chaussee"
  dataset_id: string;
  dataset_alias: string | null;
  source: "attribute_distribution" | "aggregation";
  attribute: string | null;                       // set for distribution
  aggregation: { group_by: string; metric: string | null; op: string } | null;
  total_features: number;
  series: { label: string; value: number; percent: number | null }[];
  truncated: boolean;                             // true if rolled into "Autres" or simply cut
}
```

## 4. Backend

### 4.1 `services/chart_data.py` (new)

```python
TOP_N_CAP = 10  # categorical: keep top N, roll rest into "Autres" (additive ops only)

def top_values_for_chart(
    geojson: dict,
    attribute: str,
    chart_type: Literal["bar", "pie"],
    dataset_id: str,
    dataset_alias: str | None,
) -> ChartData:
    """Frequency of an attribute's values. Compatible with bar and pie."""
    # 1. Validate attribute exists in any feature → KeyError if not
    # 2. Count occurrences (skip null), sort desc
    # 3. If distinct > TOP_N_CAP, keep top N, sum the tail into "Autres" (always additive here)
    # 4. Build series [{label, value, percent}] with percent over non-null total
    # 5. Title = f"Fréquence — {attribute}"
    # 6. Return ChartData(chart_type=..., source="attribute_distribution", ...)

def aggregation_for_chart(
    geojson: dict,
    group_by: str,
    metric: str | None,
    op: AggregateOp,
    dataset_id: str,
    dataset_alias: str | None,
) -> ChartData:
    """Run an aggregation, package as ChartData (grouped_bar)."""
    # 1. Delegate the math to services.spatial_ops.aggregate(...)
    # 2. Convert {groups: [{key, value}]} → series
    # 3. Sort desc; cap to TOP_N_CAP. Add "Autres" bucket ONLY when op in {count, sum};
    #    for mean/min/max, truncate without a synthetic bucket (no meaningful rollup).
    # 4. percent computed only when additive
    # 5. Title = f"{op}({metric}) par {group_by}" — or f"count par {group_by}" when op="count"
    # 6. Return ChartData(chart_type="grouped_bar", source="aggregation", ...)
```

Both tools pass `dataset_id` and `dataset_alias` (read from `services.store.get_meta(...)`) into
the service so the returned `ChartData` is self-contained.

### 4.2 Pydantic models (`models.py`)

```python
class ChartSeriesPoint(BaseModel):
    label: str
    value: float
    percent: float | None = None

class ChartData(BaseModel):
    chart_type: Literal["bar", "pie", "grouped_bar"]
    title: str
    dataset_id: str
    dataset_alias: str | None
    source: Literal["attribute_distribution", "aggregation"]
    attribute: str | None = None
    aggregation: dict | None = None  # {group_by, metric, op}
    total_features: int
    series: list[ChartSeriesPoint]
    truncated: bool = False
```

### 4.3 Tools

Mirror `aggregate.py`: return the dict directly (small payload, no need for an `inspection_command`).
Located in `tools/ui/`. Each tool calls the service, then returns `chart_data.model_dump(mode="json")`
so the result is a plain dict for the LLM and LangGraph plumbing.

```python
# plot_attribute_distribution.py
@tool
async def plot_attribute_distribution(
    dataset_id: str,
    attribute: str,
    chart_type: Literal["bar", "pie"],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> dict | Command:
    """Render a bar or pie chart of an attribute's value frequencies.
    Use for "show me the distribution of X", "what's the breakdown by type".
    For numerical attributes prefer describe_dataset (min/max) or plot_aggregation."""

# plot_aggregation.py
@tool
async def plot_aggregation(
    dataset_id: str,
    group_by: str,
    op: Literal["count", "sum", "mean", "min", "max"],
    tool_call_id: Annotated[str, InjectedToolCallId],
    metric: str | None = None,  # required for sum/mean/min/max
) -> dict | Command:
    """Render a grouped bar chart of <op> partitioned by <group_by>.
    Use for "total length by type", "count by borough", "average area per category"."""
```

Both tools register through `registry.py` and get a section in `prompts.py`, including the
keyword→tool table at the end of the prompt:

- `"répartition / fréquence / distribution / camembert / breakdown"` → `plot_attribute_distribution`
- `"compare / proportion / total par / moyenne par"` → `plot_aggregation`

### 4.4 Errors

Reuse `error_helpers`:

- `dataset_not_found` — unknown dataset id/alias (suggests available IDs)
- `bad_input` — attribute absent from schema, `op != count` without `metric`, `chart_type` invalid

No new error code.

## 5. Frontend

### 5.1 Dependencies

Add to `frontend/package.json`:

```
"echarts": "^5.5.0"
```

Import only the modules we use to keep the chart bundle small (target a few hundred KB gzipped at
most — verify with `next build` analysis before merging):

```ts
import * as echarts from "echarts/core";
import { BarChart, PieChart } from "echarts/charts";
import { GridComponent, TooltipComponent, TitleComponent, LegendComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
echarts.use([BarChart, PieChart, GridComponent, TooltipComponent, TitleComponent, LegendComponent, CanvasRenderer]);
```

No `echarts-for-react` — direct imperative use inside a `useEffect`.

### 5.2 `lib/echartsBuilders.ts`

Three pure builders + a dispatcher:

```ts
export function buildBarOption(data: ChartData): EChartsCoreOption { /* horizontal bar */ }
export function buildPieOption(data: ChartData): EChartsCoreOption { /* pie with legend */ }
export function buildGroupedBarOption(data: ChartData): EChartsCoreOption { /* vertical bar */ }

export function buildOption(data: ChartData): EChartsCoreOption {
  switch (data.chart_type) {
    case "bar": return buildBarOption(data);
    case "pie": return buildPieOption(data);
    case "grouped_bar": return buildGroupedBarOption(data);
  }
}
```

Testable without a DOM by asserting on the returned option object.

### 5.3 `components/Widgets/ChartWidget.tsx`

- "use client" component
- 240 px fixed height, fluid width (matches sidebar ~360 px)
- Visual chrome from layout option **B**: green `GRAPHIQUE` badge, title, white inner card,
  italic footer `Source: <alias|id> · <total_features> features [· top valeurs uniquement]`
- ECharts lifecycle in `useEffect`: `init` → `setOption(buildOption(data))` → register a
  `ResizeObserver` → cleanup with `chart.dispose()` and `ro.disconnect()`
- Empty `series` → render an empty state ("Aucune donnée à grapher"), do not init ECharts

### 5.4 Wiring in `GeoPage.tsx`

Two more `useCopilotAction` registrations next to the existing ones:

```tsx
const renderChartResult = () => ({ result, status }: { result: unknown; status: string }) => {
  if (status === "executing" || !result || typeof result !== "object") return <></>;
  return <ChartWidget data={result as ChartData} />;
};

useCopilotAction({ name: "plot_attribute_distribution", available: "disabled", render: renderChartResult() });
useCopilotAction({ name: "plot_aggregation",            available: "disabled", render: renderChartResult() });
```

No REST hydration needed — the tool returns the complete `ChartData`.

### 5.5 Types

`lib/types.ts` gets `ChartSeriesPoint` and `ChartData` matching §3.2.

## 6. Edge cases

### Backend

| Case | Behavior |
|---|---|
| Dataset unknown | `dataset_not_found` (helper) |
| Attribute absent from schema | `bad_input` — message lists available attributes |
| Numerical attribute passed to `plot_attribute_distribution` | Not an error: treated as categorical (top distinct values + "Autres"). Prompt advises `describe_dataset` instead but does not block. |
| Empty dataset (0 feature) | `ChartData(series=[], total_features=0, truncated=false)` — frontend shows empty state |
| All values null for that attribute | Same as empty: `series=[]` |
| `op != "count"` without `metric` | `bad_input` |
| `group_by` not in schema | `bad_input` |
| Categories > 10, additive op | Top 10 + `"Autres"` bucket, `truncated: true` |
| Categories > 10, mean/min/max | Top 10 only (no synthetic bucket), `truncated: true` |
| Null categorical keys | Skipped from counts; `percent` computed over non-null total |
| Boolean values | Rendered as labels `"true"` / `"false"` |

### Frontend

| Case | Behavior |
|---|---|
| `status === "executing"` | Render `<></>` until tool completes |
| Empty `series` | Empty state UI, no ECharts init |
| Widget unmount mid-init | `useEffect` cleanup disposes the chart and the ResizeObserver |
| Sidebar resize | `ResizeObserver` triggers `chart.resize()` |
| New `data` prop | `useEffect` cleanup → dispose → re-init. Acceptable: a tool call produces a new widget instance. |
| SSR | `"use client"` directive ensures ECharts never runs server-side |

## 7. Testing

### Backend (`backend/tests/`)

```
tests/services/test_chart_data.py
  - test_top_values_basic
  - test_top_values_truncation_with_other_bucket
  - test_top_values_empty_dataset
  - test_top_values_attribute_not_in_schema_raises
  - test_top_values_all_null
  - test_aggregation_count_grouped
  - test_aggregation_sum_grouped_truncation_with_other
  - test_aggregation_mean_truncation_without_other

tests/agent/tools/test_plot_attribute_distribution.py
  - test_returns_chart_data_shape
  - test_dataset_not_found
  - test_bad_attribute
  - test_handles_numeric_attribute_gracefully

tests/agent/tools/test_plot_aggregation.py
  - test_count_by_attribute
  - test_sum_requires_metric
  - test_unknown_group_by
```

### Frontend (`frontend/tests/`)

```
tests/echartsBuilders.test.ts (Vitest)
  - buildBarOption: orientation horizontal, series non-empty, color applied
  - buildPieOption: type=pie, radius set, legend present
  - buildGroupedBarOption: vertical bars, xAxis categorical
  - unknown chart_type → throws

tests/e2e/charts.spec.ts (Playwright)
  - Stub the tool result via CopilotKit SSE intercept
  - Assert: canvas appears with width > 0, title visible, footer "Source: …" visible
  - Empty state: series=[] → assert "Aucune donnée à grapher" rendered
```

### Manual golden path

Before marking the ticket done, in the running app:

1. Draw a zone, ask `« trouve les chaussées dans cette zone »`
2. Ask `« montre-moi la répartition des types de chaussées »` → bar chart appears
3. Ask `« en camembert »` → pie chart
4. Ask `« total de la longueur par type »` → grouped bar
5. Ask for a non-existent attribute → error shows in the chat

## 8. Files touched

```
backend/geo_agent/services/chart_data.py                    NEW
backend/geo_agent/agent/tools/ui/plot_attribute_distribution.py  NEW
backend/geo_agent/agent/tools/ui/plot_aggregation.py             NEW
backend/geo_agent/models.py                                  EXT (ChartData, ChartSeriesPoint)
backend/geo_agent/agent/registry.py                          EXT (register 2 tools)
backend/geo_agent/agent/prompts.py                           EXT (2 sections + keyword table)
backend/tests/services/test_chart_data.py                    NEW
backend/tests/agent/tools/test_plot_attribute_distribution.py    NEW
backend/tests/agent/tools/test_plot_aggregation.py               NEW

frontend/package.json                                        EXT (echarts dep)
frontend/lib/echartsBuilders.ts                              NEW
frontend/lib/types.ts                                        EXT (ChartData, ChartSeriesPoint)
frontend/components/Widgets/ChartWidget.tsx                  NEW
frontend/components/GeoPage.tsx                              EXT (2 useCopilotAction)
frontend/tests/echartsBuilders.test.ts                       NEW
frontend/tests/e2e/charts.spec.ts                            NEW
```
