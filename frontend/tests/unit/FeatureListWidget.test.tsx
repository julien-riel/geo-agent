import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FeatureListWidget } from "@/components/Widgets/FeatureListWidget";

const DATA = {
  view: "features" as const,
  dataset_id: "result_003",
  alias: "rues",
  total: 120,
  features: [
    { index: 0, properties: { nom_voie: "Rue A", longueur: 100, surface: "asphalte", arrond: "Plateau" }, geometry_type: "LineString" },
    { index: 1, properties: { nom_voie: "Rue B", longueur: 250, surface: "béton", arrond: "Sud-Ouest" }, geometry_type: "LineString" },
  ],
};

describe("FeatureListWidget", () => {
  it("renders one row per feature and shows total / displayed count", () => {
    render(<FeatureListWidget data={DATA} />);
    expect(screen.getByText("Rue A")).toBeInTheDocument();
    expect(screen.getByText("Rue B")).toBeInTheDocument();
    expect(screen.getByText(/120 features/)).toBeInTheDocument();
    expect(screen.getByText(/affichées/)).toBeInTheDocument();
  });

  it("expands a row to reveal properties not shown as columns", () => {
    render(<FeatureListWidget data={DATA} />);
    expect(screen.queryByText("Plateau")).toBeNull();
    fireEvent.click(screen.getByText("Rue A"));
    expect(screen.getByText("Plateau")).toBeInTheDocument();
  });
});
