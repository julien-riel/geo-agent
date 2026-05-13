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
    const b = evOk({
      id: "te_b",
      tool: "filter_attributes",
      started_at: 3.0,
      result_summary: "12 features → result_008",
    });
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
