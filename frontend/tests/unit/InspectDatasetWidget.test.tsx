import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InspectDatasetWidget } from "@/components/Widgets/InspectDatasetWidget";

describe("InspectDatasetWidget", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ features: [] }), { status: 200 })));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("renders SchemaWidget for view=schema using the inline sample (no fetch)", () => {
    render(
      <InspectDatasetWidget
        data={{
          view: "schema",
          dataset_id: "result_002",
          alias: "routes",
          attribute_schema: { nom_voie: "string", longueur: "number" },
          sample: { nom_voie: "Rue X", longueur: 42 },
        }}
      />
    );
    expect(screen.getByText("nom_voie")).toBeInTheDocument();
    expect(screen.getByText('"Rue X"')).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("renders FeatureWidget for view=feature", () => {
    render(
      <InspectDatasetWidget
        data={{ view: "feature", dataset_id: "result_003", alias: null, index: 0, properties: { k: 1 }, geometry_type: "Point", vertex_count: 1 }}
      />
    );
    expect(screen.getByText("FEATURE")).toBeInTheDocument();
    expect(screen.getByText("Point")).toBeInTheDocument();
  });

  it("renders FeatureListWidget for view=features", () => {
    render(
      <InspectDatasetWidget
        data={{ view: "features", dataset_id: "result_003", alias: null, total: 1, features: [{ index: 0, properties: { k: "v" }, geometry_type: "Point" }] }}
      />
    );
    expect(screen.getByText("FEATURES")).toBeInTheDocument();
    expect(screen.getByText("v")).toBeInTheDocument();
  });
});
