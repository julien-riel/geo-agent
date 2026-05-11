import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FeatureWidget } from "@/components/Widgets/FeatureWidget";

describe("FeatureWidget", () => {
  it("renders the property table and geometry summary", () => {
    render(
      <FeatureWidget
        data={{
          view: "feature",
          dataset_id: "result_003",
          alias: "rues",
          index: 2,
          properties: { nom_voie: "Rue X", longueur: 120 },
          geometry_type: "LineString",
          vertex_count: 4,
        }}
      />
    );
    expect(screen.getByText("rues")).toBeInTheDocument();
    expect(screen.getByText(/#2/)).toBeInTheDocument();
    expect(screen.getByText("nom_voie")).toBeInTheDocument();
    expect(screen.getByText('"Rue X"')).toBeInTheDocument();
    expect(screen.getByText("longueur")).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(screen.getByText("LineString")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });
});
