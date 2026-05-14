"use client";

import { ChartWidget } from "@/components/Widgets/ChartWidget";
import type { ChartData } from "@/lib/types";

const SAMPLE: ChartData = {
  chart_type: "bar",
  title: "Fréquence — type",
  dataset_id: "result_001",
  dataset_alias: "rues_test",
  source: "attribute_distribution",
  attribute: "type",
  aggregation: null,
  total_features: 100,
  series: [
    { label: "rue", value: 60, percent: 0.6 },
    { label: "boulevard", value: 25, percent: 0.25 },
    { label: "ruelle", value: 15, percent: 0.15 },
  ],
  truncated: false,
};

const EMPTY: ChartData = { ...SAMPLE, series: [] };

export default function TestChartPage() {
  if (process.env.NODE_ENV === "production") {
    return <div>not available</div>;
  }
  return (
    <main style={{ padding: 24, display: "flex", flexDirection: "column", gap: 16, maxWidth: 420 }}>
      <h1>ChartWidget — test harness</h1>
      <section data-testid="chart-populated">
        <ChartWidget data={SAMPLE} />
      </section>
      <section data-testid="chart-empty">
        <ChartWidget data={EMPTY} />
      </section>
    </main>
  );
}
