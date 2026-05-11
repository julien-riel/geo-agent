"use client";

import { useState } from "react";

import { DatasetMetaLite } from "@/lib/types";

interface Props {
  datasets: DatasetMetaLite[];
  activeLayers: string[];
  onToggle: (id: string) => void;
  onDraw: () => void;
  drawingActive: boolean;
  onClearAll: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, newAlias: string) => Promise<string | null>;
}

const OP_ICONS: Record<string, string> = {
  user_drawing: "📐",
  select_features: "🌐",
  filter_attributes: "🔍",
  aggregate: "Σ",
  spatial_overlay: "⧉",
  spatial_join: "⊕",
  transform_geometry: "↻",
};

function opIcon(op: string): string {
  return OP_ICONS[op] ?? "•";
}

type GroupKey = "zones" | "wfs" | "derived";

function groupKey(op: string): GroupKey {
  if (op === "user_drawing") return "zones";
  if (op === "select_features") return "wfs";
  return "derived";
}

const GROUP_TITLES: Record<GroupKey, string> = {
  zones: "Zones dessinées",
  wfs: "Résultats WFS",
  derived: "Dérivés",
};

const GROUP_ORDER: GroupKey[] = ["zones", "wfs", "derived"];

function groupDatasets(datasets: DatasetMetaLite[]): Record<GroupKey, DatasetMetaLite[]> {
  const out: Record<GroupKey, DatasetMetaLite[]> = { zones: [], wfs: [], derived: [] };
  for (const d of datasets) out[groupKey(d.operation)].push(d);
  for (const k of GROUP_ORDER) out[k].sort((a, b) => a.id.localeCompare(b.id));
  return out;
}

function ParentLineage({ parentIds, datasets }: { parentIds: string[]; datasets: DatasetMetaLite[] }) {
  if (parentIds.length === 0) return null;
  return (
    <div style={{ fontStyle: "italic", fontSize: 12, color: "#666", marginLeft: 28 }}>
      ←{" "}
      {parentIds.map((pid, i) => {
        const parent = datasets.find((d) => d.id === pid);
        const label = parent?.alias ?? pid;
        const isOrphan = !parent;
        return (
          <span key={pid}>
            {i > 0 && ", "}
            <span style={isOrphan ? { textDecoration: "line-through" } : undefined}>{label}</span>
          </span>
        );
      })}
    </div>
  );
}

function DatasetRow({
  d,
  visible,
  datasets,
  onToggle,
  onDelete,
  onRename,
}: {
  d: DatasetMetaLite;
  visible: boolean;
  datasets: DatasetMetaLite[];
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, newAlias: string) => Promise<string | null>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(d.alias ?? "");
  const [error, setError] = useState<string | null>(null);

  const isValidAlias = (s: string) => /^\S{1,64}$/.test(s);

  const submit = async () => {
    const trimmed = draft;
    if (trimmed === (d.alias ?? "")) {
      setEditing(false);
      setError(null);
      return;
    }
    if (!isValidAlias(trimmed)) {
      setError("non vide, sans espaces, max 64 caractères");
      return;
    }
    const err = await onRename(d.id, trimmed);
    if (err) {
      setError(err);
      return;
    }
    setEditing(false);
    setError(null);
  };

  return (
    <li style={{ padding: "4px 0", borderBottom: "1px dotted #eee" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <input
          type="checkbox"
          checked={visible}
          onChange={() => onToggle(d.id)}
          aria-label={`afficher ${d.alias ?? d.id}`}
        />
        <span aria-label={d.operation} title={d.operation}>
          {opIcon(d.operation)}
        </span>
        {editing ? (
          <input
            autoFocus
            value={draft}
            maxLength={64}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
              if (e.key === "Escape") {
                setEditing(false);
                setDraft(d.alias ?? "");
                setError(null);
              }
            }}
            onBlur={submit}
            style={{ flex: "0 1 200px" }}
            aria-label="nouvel alias"
          />
        ) : (
          <strong>{d.alias ?? d.id}</strong>
        )}
        <span style={{ color: "#666", flex: 1 }}>
          {d.feature_count} features
          {d.layer ? ` · ${d.layer}` : ""}
        </span>
        <button
          aria-label={`renommer ${d.alias ?? d.id}`}
          title="Renommer"
          onClick={() => {
            setEditing(true);
            setDraft(d.alias ?? "");
            setError(null);
          }}
          style={{ background: "transparent", border: 0, cursor: "pointer", fontSize: 14 }}
        >
          ✎
        </button>
        <button
          aria-label={`supprimer ${d.alias ?? d.id}`}
          title="Supprimer"
          onClick={() => {
            if (window.confirm("Supprimer ce dataset ?")) onDelete(d.id);
          }}
          style={{ background: "transparent", border: 0, cursor: "pointer", fontSize: 14 }}
        >
          🗑
        </button>
      </div>
      {error ? (
        <div style={{ color: "red", fontSize: 12, marginLeft: 28 }}>{error}</div>
      ) : null}
      <ParentLineage parentIds={d.parent_ids} datasets={datasets} />
    </li>
  );
}

export function DatasetPanel({
  datasets,
  activeLayers,
  onToggle,
  onDraw,
  drawingActive,
  onClearAll,
  onDelete,
  onRename,
}: Props) {
  const grouped = groupDatasets(datasets);

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
        maxHeight: 240,
        overflow: "auto",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <strong>Datasets ({datasets.length})</strong>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={onDraw} disabled={drawingActive}>
            {drawingActive ? "Dessine sur la carte…" : "Dessiner zone"}
          </button>
          <button
            onClick={() => {
              if (window.confirm("Effacer tous les datasets ? La conversation continue.")) {
                onClearAll();
              }
            }}
            disabled={datasets.length === 0}
            aria-label="Tout effacer"
            title="Effacer tous les datasets"
          >
            🗑 Tout effacer
          </button>
        </div>
      </div>
      {datasets.length === 0 && <em>Aucun dataset. Dessine une zone et demande à l&apos;agent.</em>}
      {GROUP_ORDER.map((g) =>
        grouped[g].length === 0 ? null : (
          <section key={g} style={{ marginBottom: 8 }}>
            <h4 style={{ fontSize: 12, color: "#444", margin: "8px 0 4px" }}>
              {GROUP_TITLES[g]} ({grouped[g].length})
            </h4>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {grouped[g].map((d) => (
                <DatasetRow
                  key={d.id}
                  d={d}
                  visible={activeLayers.includes(d.id)}
                  datasets={datasets}
                  onToggle={onToggle}
                  onDelete={onDelete}
                  onRename={onRename}
                />
              ))}
            </ul>
          </section>
        )
      )}
    </div>
  );
}
