"use client";

export function AnalysisProgress({ label }: { label: string }) {
  return (
    <div style={{ padding: 6, fontStyle: "italic", color: "#666" }}>⏳ {label}…</div>
  );
}
