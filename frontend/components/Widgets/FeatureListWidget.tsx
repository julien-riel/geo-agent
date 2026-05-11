"use client";

import React, { useState } from "react";

export interface FeatureRow {
  index: number;
  properties: Record<string, unknown>;
  geometry_type: string | null;
}

export interface FeatureListWidgetData {
  view: "features";
  dataset_id: string;
  alias: string | null;
  total: number;
  features: FeatureRow[];
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  return String(v);
}

export function FeatureListWidget({ data }: { data: FeatureListWidgetData }) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const rows = data.features ?? [];

  const cols: string[] = [];
  for (const r of rows) {
    for (const k of Object.keys(r.properties ?? {})) {
      if (!cols.includes(k)) cols.push(k);
      if (cols.length >= 3) break;
    }
    if (cols.length >= 3) break;
  }

  const toggle = (i: number) =>
    setOpen((prev) => {
      const n = new Set(prev);
      if (n.has(i)) n.delete(i);
      else n.add(i);
      return n;
    });

  return (
    <div style={card}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={badge}>FEATURES</span>
        <strong style={{ fontSize: 15 }}>{data.alias ?? data.dataset_id}</strong>
        <span style={{ color: "#64748b", fontSize: 12 }}>
          · {data.total} features{data.total > rows.length ? ` (affichées : ${rows.length})` : ""}
        </span>
      </div>

      <div style={{ background: "white", borderRadius: 6, border: "1px solid #e2e8f0", overflow: "auto", maxHeight: 320 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ background: "#f1f5f9", textAlign: "left" }}>
              <th style={th}>#</th>
              {cols.map((c) => (
                <th key={c} style={th}>{c}</th>
              ))}
              <th style={th}>géom.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const isOpen = open.has(r.index);
              return (
                <React.Fragment key={r.index}>
                  <tr style={{ borderTop: "1px solid #f1f5f9", cursor: "pointer" }} onClick={() => toggle(r.index)}>
                    <td style={td}>{r.index}</td>
                    {cols.map((c) => (
                      <td key={c} style={td}>{fmt((r.properties ?? {})[c])}</td>
                    ))}
                    <td style={td}>{r.geometry_type ?? "—"}</td>
                  </tr>
                  {isOpen && (
                    <tr key={`${r.index}-detail`}>
                      <td colSpan={cols.length + 2} style={{ padding: "6px 10px", background: "#f8fafc" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                          <tbody>
                            {Object.entries(r.properties ?? {}).map(([k, v]) => (
                              <tr key={k}>
                                <td style={{ padding: "3px 6px", color: "#64748b", fontFamily: "monospace" }}>{k}</td>
                                <td style={{ padding: "3px 6px", textAlign: "right" }}>{fmt(v)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const card: React.CSSProperties = { background: "#f8fafc", padding: 16, borderRadius: 8, fontFamily: "system-ui", fontSize: 13, color: "#0f172a" };
const badge: React.CSSProperties = { background: "#0ea5e9", color: "white", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 };
const th: React.CSSProperties = { padding: "6px 10px", fontWeight: 600, color: "#475569", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 };
const td: React.CSSProperties = { padding: "6px 10px" };
