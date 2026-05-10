import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MetadataWidget } from "@/components/Widgets/MetadataWidget";

// After Task 6, the schema toggle mounts a real SchemaWidget that fetches
// /api/datasets/<id> to populate the example column. Stub it here so the
// toggle test doesn't surface unhandled rejections.
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 404 })));
});
afterEach(() => {
  vi.unstubAllGlobals();
});

const META = {
  id: "result_002",
  alias: "routes_in_zone_1",
  source: { type: "derived" as const, layer: "geobase:chaussee", filter_summary: "" },
  feature_count: 1247,
  bbox: [-73.6, 45.5, -73.55, 45.55] as [number, number, number, number],
  attribute_schema: { id_chaussee: "number", nom_voie: "string" },
  lineage: { parent_ids: ["zone_1"], operation: "select_features", params: {} },
  created_at: "2026-05-10T12:00:00Z",
  size_bytes: 412345,
};

describe("MetadataWidget", () => {
  it("renders id, alias and the three stat tiles", () => {
    render(<MetadataWidget data={META} datasetId="result_002" status="complete" />);
    // Alias appears in both the header and the breadcrumb terminus.
    expect(screen.getAllByText("routes_in_zone_1").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("result_002")).toBeInTheDocument(); // id only in header (terminus shows alias, not id)
    expect(screen.getByText("1 247")).toBeInTheDocument(); // feature_count formatted
    expect(screen.getByText("geobase:chaussee")).toBeInTheDocument();
    expect(screen.getByText(/412/)).toBeInTheDocument(); // size in KB
  });

  it("renders the breadcrumb terminus with the dataset alias", () => {
    render(<MetadataWidget data={META} datasetId="result_002" status="complete" />);
    // Both header and breadcrumb terminus render the alias — at least 2 occurrences.
    const matches = screen.getAllByText("routes_in_zone_1");
    expect(matches.length).toBeGreaterThanOrEqual(2);
  });

  it("renders the lineage breadcrumb", () => {
    render(<MetadataWidget data={META} datasetId="result_002" status="complete" />);
    expect(screen.getByText("zone_1")).toBeInTheDocument();
    expect(screen.getByText("select_features")).toBeInTheDocument();
  });

  it("calls onShowOnMap when 'Afficher sur la carte' is clicked", () => {
    const onShowOnMap = vi.fn();
    render(
      <MetadataWidget
        data={META}
        datasetId="result_002"
        status="complete"
        onShowOnMap={onShowOnMap}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /Afficher sur la carte/i }));
    expect(onShowOnMap).toHaveBeenCalledWith("result_002");
  });

  it("toggles to schema mode when 'Voir le schéma' is clicked", () => {
    render(<MetadataWidget data={META} datasetId="result_002" status="complete" />);
    fireEvent.click(screen.getByRole("button", { name: /Voir le schéma/i }));
    // Schema mode shows the attribute names
    expect(screen.getByText("id_chaussee")).toBeInTheDocument();
    expect(screen.getByText("nom_voie")).toBeInTheDocument();
  });

  it("renders a skeleton when status is executing", () => {
    render(<MetadataWidget data={META} datasetId="result_002" status="executing" />);
    expect(screen.getByTestId("metadata-skeleton")).toBeInTheDocument();
  });
});
