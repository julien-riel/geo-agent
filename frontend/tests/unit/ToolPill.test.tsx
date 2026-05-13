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
