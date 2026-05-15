import { describe, expect, it } from "vitest";

import { buildOption, buildBarOption, buildPieOption, buildGroupedBarOption } from "@/lib/echartsBuilders";
import type { ChartData } from "@/lib/types";

const baseData = (overrides: Partial<ChartData> = {}): ChartData => ({
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
  ...overrides,
});

describe("buildBarOption", () => {
  it("produces a horizontal bar option with category yAxis", () => {
    const opt = buildBarOption(baseData());
    // @ts-expect-error — opt is loosely typed
    expect(opt.yAxis.type).toBe("category");
    // @ts-expect-error
    expect(opt.yAxis.data).toEqual(["rue", "boulevard"]);
    // @ts-expect-error
    expect(opt.xAxis.type).toBe("value");
    // @ts-expect-error
    expect(opt.series[0].type).toBe("bar");
    // @ts-expect-error
    expect(opt.series[0].data).toEqual([2, 1]);
  });
});

describe("buildPieOption", () => {
  it("produces a pie option with series.data {name, value}", () => {
    const data = baseData({ chart_type: "pie" });
    const opt = buildPieOption(data);
    // @ts-expect-error
    expect(opt.series[0].type).toBe("pie");
    // @ts-expect-error
    expect(opt.series[0].data).toEqual([
      { name: "rue", value: 2 },
      { name: "boulevard", value: 1 },
    ]);
  });
});

describe("buildGroupedBarOption", () => {
  it("produces a vertical bar option with category xAxis", () => {
    const data = baseData({
      chart_type: "grouped_bar",
      source: "aggregation",
      attribute: null,
      aggregation: { group_by: "type", metric: "v", op: "sum" },
      title: "sum(v) par type",
    });
    const opt = buildGroupedBarOption(data);
    // @ts-expect-error
    expect(opt.xAxis.type).toBe("category");
    // @ts-expect-error
    expect(opt.xAxis.data).toEqual(["rue", "boulevard"]);
    // @ts-expect-error
    expect(opt.yAxis.type).toBe("value");
    // @ts-expect-error
    expect(opt.series[0].data).toEqual([2, 1]);
  });
});

describe("buildOption (dispatcher)", () => {
  it("routes by chart_type", () => {
    expect(buildOption(baseData({ chart_type: "bar" }))).toEqual(buildBarOption(baseData()));
    const pie = baseData({ chart_type: "pie" });
    expect(buildOption(pie)).toEqual(buildPieOption(pie));
    const gb = baseData({ chart_type: "grouped_bar" });
    expect(buildOption(gb)).toEqual(buildGroupedBarOption(gb));
  });

  it("throws on unknown chart_type", () => {
    expect(() => buildOption({ ...baseData(), chart_type: "scatter" as unknown as "bar" })).toThrow();
  });
});
