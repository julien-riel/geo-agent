import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChartWidget } from "@/components/Widgets/ChartWidget";
import type { ChartData } from "@/lib/types";

// jsdom does not implement canvas; stub ECharts init to a no-op chart object.
vi.mock("@/lib/echartsBuilders", async () => {
  const actual = await vi.importActual<typeof import("@/lib/echartsBuilders")>("@/lib/echartsBuilders");
  return {
    ...actual,
    echarts: {
      ...actual.echarts,
      init: () => ({
        setOption: vi.fn(),
        resize: vi.fn(),
        dispose: vi.fn(),
      }),
    },
  };
});

const DATA: ChartData = {
  chart_type: "bar",
  title: "Fréquence — type",
  dataset_id: "result_001",
  dataset_alias: "rues",
  source: "attribute_distribution",
  attribute: "type",
  aggregation: null,
  total_features: 3,
  series: [
    { label: "rue", value: 2, percent: 0.67 },
    { label: "boulevard", value: 1, percent: 0.33 },
  ],
  truncated: false,
};

describe("ChartWidget", () => {
  it("renders title and source footer", () => {
    render(<ChartWidget data={DATA} />);
    expect(screen.getByText("Fréquence — type")).toBeInTheDocument();
    expect(screen.getByText(/rues/)).toBeInTheDocument();
    expect(screen.getByText(/3 features/)).toBeInTheDocument();
  });

  it("uses dataset_id when alias is null", () => {
    render(<ChartWidget data={{ ...DATA, dataset_alias: null }} />);
    expect(screen.getByText(/result_001/)).toBeInTheDocument();
  });

  it("mentions 'top valeurs uniquement' when truncated", () => {
    render(<ChartWidget data={{ ...DATA, truncated: true }} />);
    expect(screen.getByText(/top valeurs uniquement/)).toBeInTheDocument();
  });

  it("shows empty state when series is empty", () => {
    render(<ChartWidget data={{ ...DATA, series: [] }} />);
    expect(screen.getByText(/Aucune donnée à grapher/i)).toBeInTheDocument();
  });

  it("renders the GRAPHIQUE badge", () => {
    render(<ChartWidget data={DATA} />);
    expect(screen.getByText("GRAPHIQUE")).toBeInTheDocument();
  });
});
