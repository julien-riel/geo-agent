"use client";

import React, { useEffect, useState } from "react";
import { AttributeStatsRow } from "./AttributeStatsRow";

interface Props {
  data: {
    id: string;
    alias: string | null;
    attribute_schema: Record<string, string>;
  };
  datasetId: string;
  sample?: Record<string, unknown>;
}

const TYPE_STYLES: Record<string, { bg: string; fg: string }> = {
  number: { bg: "#dbeafe", fg: "#1e40af" },
  string: { bg: "#dcfce7", fg: "#166534" },
  boolean: { bg: "#fef3c7", fg: "#854d0e" },
};

function formatExample(v: unknown): string {
  if (v === undefined || v === null) return "—";
  if (typeof v === "string") return `"${v}"`;
  return String(v);
}

export function SchemaWidget({ data, datasetId, sample }: Props) {
  const [example, setExample] = useState<Record<string, unknown> | null>(sample ?? null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (sample) return; // already supplied — no need to fetch the first feature
    fetch(`/api/datasets/${encodeURIComponent(datasetId)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("fetch failed"))))
      .then((gj) => setExample(gj.features?.[0]?.properties ?? {}))
      .catch(() => setExample({}));
  }, [datasetId, sample]);

  const toggle = (attr: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(attr)) next.delete(attr);
      else next.add(attr);
      return next;
    });
  };

  const attrs = Object.entries(data.attribute_schema);

  return (
    <div style={{ background: "#f8fafc", padding: 16, borderRadius: 8, fontFamily: "system-ui", fontSize: 13, color: "#0f172a" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={{ background: "#8b5cf6", color: "white", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 }}>SCHÉMA</span>
        <strong style={{ fontSize: 15 }}>{data.alias ?? data.id}</strong>
        <span style={{ color: "#64748b", fontSize: 12 }}>· {attrs.length} attributs</span>
      </div>

      <div style={{ background: "white", borderRadius: 6, border: "1px solid #e2e8f0", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ background: "#f1f5f9", textAlign: "left" }}>
              <th style={th}>Attribut</th>
              <th style={th}>Type</th>
              <th style={{ ...th, textAlign: "right" }}>Exemple</th>
            </tr>
          </thead>
          <tbody>
            {attrs.map(([name, type]) => {
              const isOpen = expanded.has(name);
              const style = TYPE_STYLES[type] ?? { bg: "#e2e8f0", fg: "#0f172a" };
              return (
                <React.Fragment key={name}>
                  <tr
                    style={{ borderTop: "1px solid #f1f5f9", cursor: "pointer" }}
                    onClick={() => toggle(name)}
                  >
                    <td style={{ padding: "6px 10px", fontFamily: "monospace", fontWeight: 500 }}>{name}</td>
                    <td style={{ padding: "6px 10px" }}>
                      <span style={{ background: style.bg, color: style.fg, padding: "1px 6px", borderRadius: 3, fontSize: 10, fontFamily: "monospace" }}>{type}</span>
                    </td>
                    <td style={{ padding: "6px 10px", textAlign: "right", color: "#64748b", fontFamily: type === "number" ? "monospace" : "inherit" }}>
                      {example ? formatExample(example[name]) : "…"}
                    </td>
                  </tr>
                  {isOpen && (
                    <tr key={`${name}-stats`}>
                      <td colSpan={3} style={{ padding: 0 }}>
                        <AttributeStatsRow datasetId={datasetId} attribute={name} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div style={{ fontSize: 11, color: "#64748b", marginTop: 8, fontStyle: "italic" }}>
        Échantillon tiré de la 1ʳᵉ feature. Clique une ligne pour les stats.
      </div>
    </div>
  );
}

const th: React.CSSProperties = {
  padding: "6px 10px",
  fontWeight: 600,
  color: "#475569",
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: 0.5,
};
