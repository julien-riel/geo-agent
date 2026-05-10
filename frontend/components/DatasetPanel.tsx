"use client";

import { DatasetMetaLite } from "@/lib/types";

interface Props {
  datasets: DatasetMetaLite[];
  activeLayers: string[];
  onToggle: (id: string) => void;
  onDraw: () => void;
  drawingActive: boolean;
}

export function DatasetPanel({ datasets, activeLayers, onToggle, onDraw, drawingActive }: Props) {
  return (
    <div
      style={{
        position: "absolute",
        bottom: 0,
        left: 0,
        right: "30%",
        background: "rgba(255,255,255,0.95)",
        borderTop: "1px solid #ddd",
        padding: 12,
        maxHeight: 200,
        overflow: "auto",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <strong>Datasets ({datasets.length})</strong>
        <button onClick={onDraw} disabled={drawingActive}>
          {drawingActive ? "Dessine sur la carte…" : "Dessiner zone"}
        </button>
      </div>
      {datasets.length === 0 && <em>Aucun dataset. Dessine une zone et demande à l&apos;agent.</em>}
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {datasets.map((d) => {
          const visible = activeLayers.includes(d.id);
          const isZone = d.operation === "user_drawing";
          return (
            <li key={d.id} style={{ padding: "4px 0", borderBottom: "1px dotted #eee" }}>
              <label style={{ cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={visible}
                  onChange={() => onToggle(d.id)}
                  style={{ marginRight: 8 }}
                />
                {isZone && <span style={{ marginRight: 6 }} aria-label="zone dessinée">📐</span>}
                <strong>{d.alias ?? d.id}</strong>
                <span style={{ color: "#666", marginLeft: 8 }}>
                  {d.feature_count} features · {d.layer ?? (isZone ? "user-drawn" : "derived")} · {d.operation}
                </span>
              </label>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
