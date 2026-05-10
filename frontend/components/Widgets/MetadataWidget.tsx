"use client";

import { useState } from "react";
import { SchemaWidget } from "./SchemaWidget";

interface DatasetMetaPayload {
  id: string;
  alias: string | null;
  source: { type: string; layer: string | null; filter_summary: string };
  feature_count: number;
  bbox: [number, number, number, number];
  attribute_schema: Record<string, string>;
  lineage: { parent_ids: string[]; operation: string; params: Record<string, unknown> };
  created_at: string;
  size_bytes: number;
}

interface Props {
  data: DatasetMetaPayload;
  datasetId: string;
  status: "executing" | "complete" | "inProgress";
  onShowOnMap?: (id: string) => void;
  onFitMap?: (bbox: [number, number, number, number]) => void;
}

function formatCount(n: number): string {
  return n.toLocaleString("fr-CA").replace(/ /g, " ").replace(/,/g, " ");
}

function formatSize(bytes: number): string {
  if (bytes < 1000) return `${bytes} B`;
  if (bytes < 1000 * 1000) return `${Math.round(bytes / 1000)} KB`;
  return `${(bytes / 1000 / 1000).toFixed(1)} MB`;
}

export function MetadataWidget({ data, datasetId, status, onShowOnMap, onFitMap }: Props) {
  const [showSchema, setShowSchema] = useState(false);

  if (status === "executing") {
    return (
      <div data-testid="metadata-skeleton" style={{ padding: 12, background: "#f1f5f9", borderRadius: 8 }}>
        <em style={{ color: "#94a3b8" }}>Chargement…</em>
      </div>
    );
  }

  if (showSchema) {
    return <SchemaWidget data={data} datasetId={datasetId} />;
  }

  const layerLabel = data.source?.layer ?? data.lineage.operation;

  return (
    <div style={{ background: "#f8fafc", padding: 16, borderRadius: 8, fontFamily: "system-ui", fontSize: 13, color: "#0f172a" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={{ background: "#3b82f6", color: "white", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 }}>DATASET</span>
        <strong style={{ fontSize: 15 }}>{data.alias ?? data.id}</strong>
        <span style={{ color: "#64748b", fontFamily: "monospace", fontSize: 11 }}>{data.id}</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, marginBottom: 12 }}>
        <Tile label="Features" value={formatCount(data.feature_count)} />
        <Tile label="Couche" value={layerLabel} />
        <Tile label="Taille" value={formatSize(data.size_bytes)} />
      </div>

      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>Lignée</div>
        <Lineage parents={data.lineage.parent_ids} operation={data.lineage.operation} current={data.id} />
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button onClick={() => setShowSchema(true)} style={btnPrimary}>Voir le schéma</button>
        <button onClick={() => onShowOnMap?.(datasetId)} style={btnSecondary}>Afficher sur la carte</button>
        <button onClick={() => onFitMap?.(data.bbox)} style={btnSecondary}>Cadrer la carte</button>
      </div>
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: "white", padding: 8, borderRadius: 6, border: "1px solid #e2e8f0" }}>
      <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 600, color: "#0f172a" }}>{value}</div>
    </div>
  );
}

function Lineage({ parents, operation }: { parents: string[]; operation: string; current: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, flexWrap: "wrap" }}>
      {parents.map((p) => (
        <span key={p}>
          <span style={{ background: "#fef3c7", padding: "2px 6px", borderRadius: 3, fontFamily: "monospace" }}>{p}</span>
          <span style={{ color: "#94a3b8", margin: "0 6px" }}>→</span>
        </span>
      ))}
      <span style={{ background: "#dbeafe", padding: "2px 6px", borderRadius: 3, fontFamily: "monospace" }}>{operation}</span>
    </div>
  );
}

const btnPrimary = { background: "#3b82f6", color: "white", border: "none", padding: "6px 12px", borderRadius: 5, fontSize: 12, cursor: "pointer" } as const;
const btnSecondary = { background: "white", border: "1px solid #e2e8f0", color: "#0f172a", padding: "6px 12px", borderRadius: 5, fontSize: 12, cursor: "pointer" } as const;
