"use client";

import { useEffect } from "react";
import { useSelectedFeature } from "@/lib/selectedFeature";
import { useMap } from "./MapView";

const DEFAULT_PAINT = {
  fill: { "fill-color": "#3b82f6", "fill-opacity": 0.3, "fill-outline-color": "#1e40af" },
  line: { "line-color": "#ef4444", "line-width": 2 },
  circle: { "circle-radius": 5, "circle-color": "#10b981" },
} as const;

const DIMMED = {
  fill: { "fill-opacity": 0.08 },
  line: { "line-opacity": 0.15 },
  circle: { "circle-opacity": 0.2 },
} as const;

export function DatasetLayer({ datasetId }: { datasetId: string }) {
  const map = useMap();
  const { selected, setSelected } = useSelectedFeature();

  useEffect(() => {
    if (!map) return;
    const sourceId = `ds-${datasetId}`;
    const url = `/api/datasets/${datasetId}`;

    if (!map.getSource(sourceId)) {
      map.addSource(sourceId, { type: "geojson", data: url });
      map.addLayer({ id: `${sourceId}-fill`, source: sourceId, type: "fill", filter: ["==", ["geometry-type"], "Polygon"], paint: DEFAULT_PAINT.fill });
      map.addLayer({ id: `${sourceId}-line`, source: sourceId, type: "line", filter: ["==", ["geometry-type"], "LineString"], paint: DEFAULT_PAINT.line });
      map.addLayer({ id: `${sourceId}-circle`, source: sourceId, type: "circle", filter: ["==", ["geometry-type"], "Point"], paint: DEFAULT_PAINT.circle });
    }

    const layerIds = [`${sourceId}-fill`, `${sourceId}-line`, `${sourceId}-circle`];
    const handler = (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
      const f = e.features?.[0];
      if (!f) return;
      const lngLat: [number, number] = [e.lngLat.lng, e.lngLat.lat];
      fetch(url)
        .then((r) => r.json())
        .then((gj: GeoJSON.FeatureCollection) => {
          const idx = gj.features.findIndex((g) => JSON.stringify(g.properties) === JSON.stringify(f.properties));
          const feature = idx >= 0 ? gj.features[idx] : (f as unknown as GeoJSON.Feature);
          setSelected({ datasetId, index: idx, feature, lngLat });
        })
        .catch(() => {
          setSelected({ datasetId, index: -1, feature: f as unknown as GeoJSON.Feature, lngLat });
        });
    };
    for (const lid of layerIds) map.on("click", lid, handler);

    return () => {
      for (const lid of layerIds) {
        map.off("click", lid, handler);
        if (map.getLayer(lid)) map.removeLayer(lid);
      }
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    };
  }, [map, datasetId, setSelected]);

  // Apply dim/restore based on selection.
  useEffect(() => {
    if (!map) return;
    const sourceId = `ds-${datasetId}`;
    const isThisDataset = selected?.datasetId === datasetId;
    const apply = (lid: string, def: Record<string, unknown>, dim: Record<string, unknown>) => {
      if (!map.getLayer(lid)) return;
      const props = isThisDataset ? dim : def;
      for (const [k, v] of Object.entries(props)) {
        map.setPaintProperty(lid, k, v as never);
      }
    };
    apply(`${sourceId}-fill`, DEFAULT_PAINT.fill, DIMMED.fill);
    apply(`${sourceId}-line`, DEFAULT_PAINT.line, DIMMED.line);
    apply(`${sourceId}-circle`, DEFAULT_PAINT.circle, DIMMED.circle);
  }, [map, datasetId, selected]);

  return null;
}
