"use client";

import { useEffect, useState } from "react";

interface Stats {
  attribute: string;
  type: "number" | "string" | "boolean";
  non_null_count: number;
  null_count: number;
  distinct_count: number;
  min?: number;
  max?: number;
  top_values?: Array<{ value: unknown; count: number }>;
}

interface Props {
  datasetId: string;
  attribute: string;
}

export function AttributeStatsRow({ datasetId, attribute }: Props) {
  const [state, setState] = useState<{ kind: "loading" } | { kind: "ok"; stats: Stats } | { kind: "error"; message: string }>({ kind: "loading" });

  useEffect(() => {
    fetch(`/api/datasets/${encodeURIComponent(datasetId)}/attributes/${encodeURIComponent(attribute)}/stats`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((stats: Stats) => setState({ kind: "ok", stats }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }, [datasetId, attribute]);

  if (state.kind === "loading") {
    return <div style={{ padding: "6px 10px", fontSize: 11, color: "#64748b", fontStyle: "italic" }}>Chargement des stats…</div>;
  }
  if (state.kind === "error") {
    return <div style={{ padding: "6px 10px", fontSize: 11, color: "#b91c1c" }}>Erreur : {state.message}</div>;
  }

  const s = state.stats;

  return (
    <div style={{ padding: "8px 10px", background: "#f8fafc", borderTop: "1px solid #e2e8f0", fontSize: 11 }}>
      <div style={{ display: "flex", gap: 16, color: "#475569" }}>
        <span>Non null : <strong>{s.non_null_count}</strong></span>
        <span>Null : <strong>{s.null_count}</strong></span>
        <span>Distinctes : <strong>{s.distinct_count}</strong></span>
        {s.min !== undefined && <span>Min : <strong>{s.min}</strong></span>}
        {s.max !== undefined && <span>Max : <strong>{s.max}</strong></span>}
      </div>
      {s.top_values && s.top_values.length > 0 && (
        <div style={{ marginTop: 6 }}>
          <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 2 }}>Top valeurs</div>
          <ul style={{ margin: 0, paddingLeft: 16, color: "#0f172a" }}>
            {s.top_values.slice(0, 5).map((tv, i) => (
              <li key={i}><code>{String(tv.value)}</code> · {tv.count}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
