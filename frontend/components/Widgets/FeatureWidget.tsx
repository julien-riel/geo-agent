"use client";

import React from "react";

export interface FeatureWidgetData {
  view: "feature";
  dataset_id: string;
  alias: string | null;
  index: number;
  properties: Record<string, unknown>;
  geometry_type: string | null;
  vertex_count: number;
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return `"${v}"`;
  return String(v);
}

export function FeatureWidget({ data }: { data: FeatureWidgetData }) {
  const props = data.properties ?? {};
  return (
    <div style={card}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={badge}>FEATURE</span>
        <strong style={{ fontSize: 15 }}>{data.alias ?? data.dataset_id}</strong>
        <span style={{ color: "#64748b", fontSize: 12 }}>· #{data.index}</span>
      </div>

      <div style={sectionLabel}>Propriétés</div>
      <table style={tbl}>
        <tbody>
          {Object.entries(props).map(([k, v]) => (
            <tr key={k} style={{ borderBottom: "1px solid #f1f5f9" }}>
              <td style={{ padding: "5px 8px", color: "#64748b", fontFamily: "monospace" }}>{k}</td>
              <td style={{ padding: "5px 8px", textAlign: "right" }}>{fmt(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={sectionLabel}>Géométrie</div>
      <table style={tbl}>
        <tbody>
          <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
            <td style={{ padding: "5px 8px", color: "#64748b" }}>Type</td>
            <td style={{ padding: "5px 8px", textAlign: "right" }}>{data.geometry_type ?? "—"}</td>
          </tr>
          <tr>
            <td style={{ padding: "5px 8px", color: "#64748b" }}>Vertices</td>
            <td style={{ padding: "5px 8px", textAlign: "right", fontFamily: "monospace" }}>{data.vertex_count}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

const card: React.CSSProperties = { background: "#f8fafc", padding: 16, borderRadius: 8, fontFamily: "system-ui", fontSize: 13, color: "#0f172a" };
const badge: React.CSSProperties = { background: "#fbbf24", color: "#78350f", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 };
const sectionLabel: React.CSSProperties = { fontSize: 9, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5, margin: "10px 0 4px" };
const tbl: React.CSSProperties = { width: "100%", borderCollapse: "collapse", fontSize: 12, background: "white", border: "1px solid #e2e8f0", borderRadius: 6 };
