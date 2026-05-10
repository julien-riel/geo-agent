import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useEffect } from "react";

import { HighlightLayer } from "@/components/Map/HighlightLayer";
import { MapContext } from "@/components/Map/MapView";
import { SelectedFeatureProvider, useSelectedFeature, SelectedFeature } from "@/lib/selectedFeature";

function makeFakeMap() {
  const sources = new Map<string, { type: string; data: unknown }>();
  const layers = new Set<string>();
  const setData = vi.fn();
  return {
    spy: { setData },
    map: {
      addSource: vi.fn((id: string, src: { type: string; data: unknown }) => sources.set(id, src)),
      addLayer: vi.fn((spec: { id: string }) => layers.add(spec.id)),
      removeLayer: vi.fn((id: string) => layers.delete(id)),
      removeSource: vi.fn((id: string) => sources.delete(id)),
      getSource: vi.fn((id: string) => (sources.has(id) ? { setData } : undefined)),
      getLayer: vi.fn((id: string) => (layers.has(id) ? {} : undefined)),
    } as unknown as maplibregl.Map,
  };
}

function Setter({ value }: { value: SelectedFeature | null }) {
  const { setSelected } = useSelectedFeature();
  useEffect(() => {
    setSelected(value);
  }, [value]);
  return null;
}

describe("HighlightLayer", () => {
  it("creates the highlight source and three layers on mount", () => {
    const { map } = makeFakeMap();
    render(
      <MapContext.Provider value={map}>
        <SelectedFeatureProvider>
          <HighlightLayer />
        </SelectedFeatureProvider>
      </MapContext.Provider>
    );
    expect(map.addSource).toHaveBeenCalledWith("highlight-source", expect.objectContaining({ type: "geojson" }));
    expect(map.addLayer).toHaveBeenCalledTimes(3);
  });

  it("updates the source data when a feature is selected", () => {
    const { map, spy } = makeFakeMap();
    const feature: GeoJSON.Feature = { type: "Feature", geometry: { type: "Point", coordinates: [-73, 45] }, properties: {} };
    render(
      <MapContext.Provider value={map}>
        <SelectedFeatureProvider>
          <HighlightLayer />
          <Setter value={{ datasetId: "result_001", index: 0, feature, lngLat: [-73, 45] }} />
        </SelectedFeatureProvider>
      </MapContext.Provider>
    );
    expect(spy.setData).toHaveBeenCalledWith({ type: "FeatureCollection", features: [feature] });
  });

  it("clears the source data when selection is cleared", async () => {
    const { map, spy } = makeFakeMap();
    const { rerender } = render(
      <MapContext.Provider value={map}>
        <SelectedFeatureProvider>
          <HighlightLayer />
          <Setter value={{ datasetId: "result_001", index: 0, feature: { type: "Feature", geometry: { type: "Point", coordinates: [0, 0] }, properties: {} }, lngLat: [0, 0] }} />
        </SelectedFeatureProvider>
      </MapContext.Provider>
    );
    spy.setData.mockClear();
    rerender(
      <MapContext.Provider value={map}>
        <SelectedFeatureProvider>
          <HighlightLayer />
          <Setter value={null} />
        </SelectedFeatureProvider>
      </MapContext.Provider>
    );
    expect(spy.setData).toHaveBeenCalledWith({ type: "FeatureCollection", features: [] });
  });
});
