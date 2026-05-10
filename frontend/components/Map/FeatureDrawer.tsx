"use client";

import { useSelectedFeature } from "@/lib/selectedFeature";
import { useMap } from "./MapView";

interface Props {
  onAskAgent?: (prompt: string) => void;
}

function pickTitle(props: Record<string, unknown>, index: number): string {
  for (const key of ["nom_voie", "name", "nom", "title", "label"]) {
    const v = props[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  return `Feature #${index}`;
}

function countVertices(g: GeoJSON.Geometry): number {
  switch (g.type) {
    case "Point": return 1;
    case "MultiPoint": case "LineString": return g.coordinates.length;
    case "MultiLineString": case "Polygon": return g.coordinates.reduce((n, ring) => n + ring.length, 0);
    case "MultiPolygon": return g.coordinates.reduce((n, poly) => n + poly.reduce((m, ring) => m + ring.length, 0), 0);
    case "GeometryCollection": return g.geometries.reduce((n, gg) => n + countVertices(gg), 0);
    default: return 0;
  }
}

function bboxOf(g: GeoJSON.Geometry): [number, number, number, number] {
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  const walk = (c: unknown) => {
    if (Array.isArray(c) && typeof c[0] === "number" && typeof c[1] === "number") {
      const [x, y] = c as [number, number];
      if (x < minx) minx = x; if (x > maxx) maxx = x;
      if (y < miny) miny = y; if (y > maxy) maxy = y;
    } else if (Array.isArray(c)) {
      c.forEach(walk);
    }
  };
  if ("coordinates" in g) walk(g.coordinates);
  return [minx, miny, maxx, maxy];
}

export function FeatureDrawer({ onAskAgent }: Props) {
  const { selected, setSelected, drawerOpen } = useSelectedFeature();
  const map = useMap();

  if (!selected || !drawerOpen) return null;

  const props = (selected.feature.properties ?? {}) as Record<string, unknown>;
  const title = pickTitle(props, selected.index);
  const vertexCount = countVertices(selected.feature.geometry);

  const askAgent = () => {
    const prompt = `Au sujet de la feature #${selected.index} du dataset ${selected.datasetId} (« ${title} »), `;
    onAskAgent?.(prompt);
  };

  const fitMap = () => {
    if (!map) return;
    const [minx, miny, maxx, maxy] = bboxOf(selected.feature.geometry);
    if (Number.isFinite(minx)) map.fitBounds([[minx, miny], [maxx, maxy]], { padding: 80, maxZoom: 18 });
  };

  return (
    <div style={{
      position: "absolute", top: 0, right: 0, bottom: 0, width: 300,
      background: "white", borderLeft: "1px solid #e2e8f0", display: "flex", flexDirection: "column",
      fontFamily: "system-ui", fontSize: 12, color: "#0f172a", boxShadow: "-2px 0 8px rgba(0,0,0,0.05)", zIndex: 5,
    }}>
      <div style={{ padding: 12, borderBottom: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <span style={{ background: "#fbbf24", color: "#78350f", padding: "2px 6px", borderRadius: 3, fontSize: 10, fontWeight: 600 }}>FEATURE</span>
          <div style={{ fontSize: 14, fontWeight: 600, marginTop: 6 }}>{title}</div>
          <div style={{ fontSize: 10, color: "#64748b", fontFamily: "monospace", marginTop: 2 }}>{selected.datasetId} · #{selected.index}</div>
        </div>
        <button
          aria-label="Fermer"
          onClick={() => setSelected(null)}
          style={{ background: "none", border: "none", cursor: "pointer", color: "#94a3b8", fontSize: 18, lineHeight: 1 }}
        >×</button>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "8px 12px" }}>
        <div style={sectionLabel}>Propriétés</div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
          <tbody>
            {Object.entries(props).map(([k, v]) => (
              <tr key={k} style={{ borderBottom: "1px solid #f1f5f9" }}>
                <td style={{ padding: "5px 0", color: "#64748b", fontFamily: "monospace" }}>{k}</td>
                <td style={{ padding: "5px 0", textAlign: "right" }}>{typeof v === "string" ? `"${v}"` : String(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div style={sectionLabel}>Géométrie</div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
          <tbody>
            <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
              <td style={{ padding: "5px 0", color: "#64748b" }}>Type</td>
              <td style={{ padding: "5px 0", textAlign: "right" }}>{selected.feature.geometry.type}</td>
            </tr>
            <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
              <td style={{ padding: "5px 0", color: "#64748b" }}>Vertices</td>
              <td style={{ padding: "5px 0", textAlign: "right", fontFamily: "monospace" }}>{vertexCount}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div style={{ padding: "10px 12px", borderTop: "1px solid #f1f5f9", display: "flex", flexDirection: "column", gap: 6 }}>
        <button onClick={fitMap} style={btnPrimary}>Cadrer la carte sur la feature</button>
        <button onClick={askAgent} style={btnSecondary}>Demander à l'agent…</button>
      </div>
    </div>
  );
}

const sectionLabel: React.CSSProperties = {
  fontSize: 9, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5, margin: "8px 0 4px",
};
const btnPrimary = { background: "#3b82f6", color: "white", border: "none", padding: 7, borderRadius: 5, fontSize: 11, cursor: "pointer" } as const;
const btnSecondary = { background: "white", border: "1px solid #e2e8f0", color: "#0f172a", padding: 7, borderRadius: 5, fontSize: 11, cursor: "pointer" } as const;
