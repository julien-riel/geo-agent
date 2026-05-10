"use client";

import { useEffect } from "react";
import { useMap } from "./MapView";

export function DatasetLayer({ datasetId }: { datasetId: string }) {
  const map = useMap();

  useEffect(() => {
    if (!map) return;
    const sourceId = `ds-${datasetId}`;
    const url = `/api/datasets/${datasetId}`;

    if (!map.getSource(sourceId)) {
      map.addSource(sourceId, { type: "geojson", data: url });
      map.addLayer({
        id: `${sourceId}-fill`,
        source: sourceId,
        type: "fill",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": "#3b82f6", "fill-opacity": 0.3, "fill-outline-color": "#1e40af" },
      });
      map.addLayer({
        id: `${sourceId}-line`,
        source: sourceId,
        type: "line",
        filter: ["==", ["geometry-type"], "LineString"],
        paint: { "line-color": "#ef4444", "line-width": 2 },
      });
      map.addLayer({
        id: `${sourceId}-circle`,
        source: sourceId,
        type: "circle",
        filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-radius": 5, "circle-color": "#10b981" },
      });
    }

    return () => {
      for (const lid of [`${sourceId}-fill`, `${sourceId}-line`, `${sourceId}-circle`]) {
        if (map.getLayer(lid)) map.removeLayer(lid);
      }
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    };
  }, [map, datasetId]);

  return null;
}
