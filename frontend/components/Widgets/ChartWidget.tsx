"use client";

import { useEffect, useRef } from "react";

import { buildOption, echarts } from "@/lib/echartsBuilders";
import type { ChartData } from "@/lib/types";

interface Props {
  data: ChartData;
}

export function ChartWidget({ data }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null);
  const isEmpty = data.series.length === 0;

  useEffect(() => {
    if (isEmpty || !containerRef.current) return;
    const chart = echarts.init(containerRef.current, undefined, { renderer: "canvas" });
    chartRef.current = chart;
    chart.setOption(buildOption(data));
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(containerRef.current);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, [data, isEmpty]);

  const sourceLabel = data.dataset_alias ?? data.dataset_id;

  return (
    <div style={{ background: "#f8fafc", padding: 16, borderRadius: 8, fontFamily: "system-ui", fontSize: 13, color: "#0f172a" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={{ background: "#10b981", color: "white", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 }}>
          GRAPHIQUE
        </span>
        <strong style={{ fontSize: 14 }}>{data.title}</strong>
      </div>
      <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 6, padding: 10 }}>
        {isEmpty ? (
          <div style={{ height: 240, display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b", fontStyle: "italic" }}>
            Aucune donnée à grapher
          </div>
        ) : (
          <div ref={containerRef} style={{ width: "100%", height: 240 }} />
        )}
      </div>
      <div style={{ fontSize: 11, color: "#64748b", marginTop: 8, fontStyle: "italic" }}>
        Source : {sourceLabel} · {data.total_features} features
        {data.truncated && " · top valeurs uniquement"}
      </div>
    </div>
  );
}
