"use client";

import { useEffect } from "react";
import { TerraDraw, TerraDrawPolygonMode } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import { useMap } from "./MapView";

export function DrawTool({ onPolygon }: { onPolygon: (polygon: GeoJSON.Polygon) => void }) {
  const map = useMap();

  useEffect(() => {
    if (!map) return;
    const draw = new TerraDraw({
      adapter: new TerraDrawMapLibreGLAdapter({ map: map as any }),
      modes: [new TerraDrawPolygonMode()],
    });
    draw.start();
    draw.setMode("polygon");
    // terra-draw 1.x: finish event emits (id: FeatureId, context: OnFinishContext)
    draw.on("finish", (id, _context) => {
      const feat = draw.getSnapshotFeature(id);
      if (feat && feat.geometry.type === "Polygon") {
        onPolygon(feat.geometry as GeoJSON.Polygon);
        draw.clear();
      }
    });
    return () => {
      draw.stop();
    };
  }, [map, onPolygon]);

  return null;
}
