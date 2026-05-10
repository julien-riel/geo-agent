"use client";

import maplibregl from "maplibre-gl";
import { useEffect } from "react";
import { useSelectedFeature } from "@/lib/selectedFeature";
import { useMap } from "./MapView";

const SOURCE_ID = "highlight-source";
const LAYER_FILL = "highlight-fill";
const LAYER_LINE = "highlight-line";
const LAYER_CIRCLE = "highlight-circle";

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export function HighlightLayer() {
  const map = useMap();
  const { selected } = useSelectedFeature();

  useEffect(() => {
    if (!map) return;
    if (map.getSource(SOURCE_ID)) return;
    map.addSource(SOURCE_ID, { type: "geojson", data: EMPTY });
    map.addLayer({
      id: LAYER_FILL,
      source: SOURCE_ID,
      type: "fill",
      filter: ["==", ["geometry-type"], "Polygon"],
      paint: { "fill-color": "#fbbf24", "fill-opacity": 0.4 },
    });
    map.addLayer({
      id: LAYER_LINE,
      source: SOURCE_ID,
      type: "line",
      filter: ["==", ["geometry-type"], "LineString"],
      paint: { "line-color": "#fbbf24", "line-width": 5, "line-opacity": 0.95 },
    });
    map.addLayer({
      id: LAYER_CIRCLE,
      source: SOURCE_ID,
      type: "circle",
      filter: ["==", ["geometry-type"], "Point"],
      paint: { "circle-color": "#fbbf24", "circle-radius": 12, "circle-stroke-width": 3, "circle-stroke-color": "#92400e" },
    });
    return () => {
      for (const lid of [LAYER_FILL, LAYER_LINE, LAYER_CIRCLE]) {
        if (map.getLayer(lid)) map.removeLayer(lid);
      }
      if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
    };
  }, [map]);

  useEffect(() => {
    if (!map) return;
    const src = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    src.setData(selected ? { type: "FeatureCollection", features: [selected.feature] } : EMPTY);
  }, [map, selected]);

  return null;
}
