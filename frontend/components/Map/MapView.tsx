"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { createContext, MutableRefObject, useContext, useEffect, useRef, useState } from "react";
import { BASEMAP_STYLE_URL } from "@/lib/basemap";
import { FeaturePopup } from "./FeaturePopup";
import { HighlightLayer } from "./HighlightLayer";

export const MapContext = createContext<maplibregl.Map | null>(null);
export const useMap = () => useContext(MapContext);

interface MapViewProps {
  children?: React.ReactNode;
  mapRef?: MutableRefObject<maplibregl.Map | null>;
}

export function MapView({ children, mapRef }: MapViewProps) {
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
    m.on("load", () => {
      setMap(m);
      if (mapRef) mapRef.current = m;
      if (typeof window !== "undefined" && process.env.NODE_ENV !== "production") {
        (window as unknown as { __map: maplibregl.Map }).__map = m;
      }
    });
    return () => {
      if (mapRef) mapRef.current = null;
      m.remove();
    };
  }, [mapRef]);

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      <MapContext.Provider value={map}>
        {map && (
          <>
            <HighlightLayer />
            <FeaturePopup />
            {children}
          </>
        )}
      </MapContext.Provider>
    </div>
  );
}
