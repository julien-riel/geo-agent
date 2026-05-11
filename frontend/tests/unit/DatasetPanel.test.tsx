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
    // The derived row's lineage line references its parent (here result_002,
    // which has no alias so it renders by id). The same id also appears as the
    // WFS row's label, so scope the lookup to the derived <li>.
    const derivedRow = screen.getByText("filtre_long").closest("li") as HTMLElement;
    expect(derivedRow).not.toBeNull();
    expect(derivedRow.textContent).toContain("result_002");
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
