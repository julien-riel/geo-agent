import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useEffect } from "react";

import { FeatureDrawer } from "@/components/Map/FeatureDrawer";
import { SelectedFeatureProvider, useSelectedFeature, SelectedFeature } from "@/lib/selectedFeature";

function Setter({ value, openDrawer }: { value: SelectedFeature | null; openDrawer: boolean }) {
  const { setSelected, setDrawerOpen } = useSelectedFeature();
  useEffect(() => {
    setSelected(value);
    if (value && openDrawer) setDrawerOpen(true);
  }, [value, openDrawer]);
  return null;
}

const FEATURE: GeoJSON.Feature = {
  type: "Feature",
  geometry: { type: "LineString", coordinates: [[0, 0], [1, 1], [2, 2]] },
  properties: { id_chaussee: 8421, nom_voie: "Rue X", longueur_m: 147.3 },
};

describe("FeatureDrawer", () => {
  it("does not render when no selection", () => {
    render(
      <SelectedFeatureProvider>
        <FeatureDrawer />
      </SelectedFeatureProvider>
    );
    expect(screen.queryByText(/FEATURE/)).toBeNull();
  });

  it("does not render when selection exists but drawer not opened", () => {
    render(
      <SelectedFeatureProvider>
        <FeatureDrawer />
        <Setter value={{ datasetId: "result_002", index: 7, feature: FEATURE, lngLat: [0, 0] }} openDrawer={false} />
      </SelectedFeatureProvider>
    );
    expect(screen.queryByText(/FEATURE/)).toBeNull();
  });

  it("renders title, properties, and geometry summary when open", () => {
    render(
      <SelectedFeatureProvider>
        <FeatureDrawer />
        <Setter value={{ datasetId: "result_002", index: 7, feature: FEATURE, lngLat: [0, 0] }} openDrawer={true} />
      </SelectedFeatureProvider>
    );
    expect(screen.getByText("Rue X")).toBeInTheDocument();
    expect(screen.getByText("id_chaussee")).toBeInTheDocument();
    expect(screen.getByText("8421")).toBeInTheDocument();
    expect(screen.getByText("LineString")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument(); // vertex count
  });

  it("calls onAskAgent with prefilled prompt when 'Demander à l'agent' is clicked", () => {
    const onAskAgent = vi.fn();
    render(
      <SelectedFeatureProvider>
        <FeatureDrawer onAskAgent={onAskAgent} />
        <Setter value={{ datasetId: "result_002", index: 7, feature: FEATURE, lngLat: [0, 0] }} openDrawer={true} />
      </SelectedFeatureProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: /Demander à l'agent/i }));
    expect(onAskAgent).toHaveBeenCalledWith(
      expect.stringContaining("feature #7"),
    );
    expect(onAskAgent.mock.calls[0][0]).toMatch(/result_002/);
    expect(onAskAgent.mock.calls[0][0]).toMatch(/Rue X/);
  });
});
