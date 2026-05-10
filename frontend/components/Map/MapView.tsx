"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { BASEMAP_STYLE_URL } from "@/lib/basemap";

const MapContext = createContext<maplibregl.Map | null>(null);
export const useMap = () => useContext(MapContext);

export function MapView({ children }: { children?: React.ReactNode }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [map, setMap] = useState<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const m = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP_STYLE_URL,
      center: [-73.6, 45.5],
      zoom: 11,
    });
    m.on("load", () => setMap(m));
    return () => m.remove();
  }, []);

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      <MapContext.Provider value={map}>{map && children}</MapContext.Provider>
    </div>
  );
}
