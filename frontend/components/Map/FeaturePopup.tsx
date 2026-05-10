"use client";

import maplibregl from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useSelectedFeature } from "@/lib/selectedFeature";
import { useMap } from "./MapView";

function pickTitle(props: Record<string, unknown>): string {
  for (const key of ["nom_voie", "name", "nom", "title", "label"]) {
    const v = props[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  for (const key of Object.keys(props)) {
    const v = props[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  for (const key of Object.keys(props)) {
    const v = props[key];
    if (key.startsWith("id") && (typeof v === "number" || typeof v === "string")) {
      return `#${v}`;
    }
  }
  return "Feature";
}

function pickStats(props: Record<string, unknown>): Array<[string, string]> {
  const out: Array<[string, string]> = [];
  for (const [k, v] of Object.entries(props)) {
    if (out.length >= 2) break;
    if (typeof v === "number") out.push([k, String(v)]);
  }
  return out;
}

export function FeaturePopup() {
  const map = useMap();
  const { selected, setSelected, setDrawerOpen } = useSelectedFeature();
  const popupRef = useRef<maplibregl.Popup | null>(null);
  // Use state (not ref) so React re-renders when the container div is ready for the portal.
  const [container, setContainer] = useState<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!map || !selected) return;

    const div = document.createElement("div");
    setContainer(div);

    const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, anchor: "bottom" })
      .setLngLat(selected.lngLat)
      .setDOMContent(div)
      .addTo(map);

    popupRef.current = popup;

    popup.on("close", () => {
      setSelected(null);
    });

    return () => {
      popup.remove();
      popupRef.current = null;
      setContainer(null);
    };
  }, [map, selected?.datasetId, selected?.index]);

  if (!selected || !container) return null;

  const props = (selected.feature.properties ?? {}) as Record<string, unknown>;
  const title = pickTitle(props);
  const stats = pickStats(props);

  return createPortal(
    <div style={{ fontFamily: "system-ui", fontSize: 11, minWidth: 160 }}>
      <div style={{ fontWeight: 600, marginBottom: 4, color: "#0f172a" }}>{title}</div>
      {stats.length > 0 && (
        <div style={{ color: "#64748b", fontSize: 10, marginBottom: 6 }}>
          {stats.map(([k, v]) => `${k}: ${v}`).join(" · ")}
        </div>
      )}
      <button
        onClick={() => setDrawerOpen(true)}
        style={{ background: "transparent", border: "none", color: "#3b82f6", fontSize: 11, cursor: "pointer", padding: 0 }}
      >
        Détails →
      </button>
    </div>,
    container
  );
}
