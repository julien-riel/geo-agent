"use client";

interface Props {
  datasetId: string;
  alias: string | null;
  featureCount: number;
}

export function DatasetCard({ datasetId, alias, featureCount }: Props) {
  return (
    <div style={{ padding: 8, border: "1px solid #ddd", borderRadius: 6, marginTop: 6 }}>
      <strong>{alias ?? datasetId}</strong>
      <div style={{ color: "#666", fontSize: 12 }}>{featureCount} features</div>
    </div>
  );
}
