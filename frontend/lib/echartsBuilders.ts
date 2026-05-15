import * as echarts from "echarts/core";
import { BarChart, PieChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  TitleComponent,
  LegendComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";

import type { ChartData } from "@/lib/types";

echarts.use([
  BarChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  TitleComponent,
  LegendComponent,
  CanvasRenderer,
]);

const BAR_COLOR = "#3b82f6";

export function buildBarOption(data: ChartData): EChartsCoreOption {
  return {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 90, right: 30, top: 10, bottom: 24 },
    xAxis: { type: "value" },
    yAxis: {
      type: "category",
      data: data.series.map((p) => p.label),
      axisLabel: { fontSize: 11 },
      inverse: true,
    },
    series: [
      {
        type: "bar",
        data: data.series.map((p) => p.value),
        itemStyle: { color: BAR_COLOR, borderRadius: [0, 2, 2, 0] },
      },
    ],
  };
}

export function buildPieOption(data: ChartData): EChartsCoreOption {
  return {
    tooltip: { trigger: "item" },
    legend: { orient: "vertical", left: "left", textStyle: { fontSize: 11 } },
    series: [
      {
        type: "pie",
        radius: ["35%", "70%"],
        center: ["65%", "50%"],
        data: data.series.map((p) => ({ name: p.label, value: p.value })),
        label: { fontSize: 11 },
      },
    ],
  };
}

export function buildGroupedBarOption(data: ChartData): EChartsCoreOption {
  return {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 50, right: 20, top: 10, bottom: 40 },
    xAxis: {
      type: "category",
      data: data.series.map((p) => p.label),
      axisLabel: { fontSize: 11, rotate: 30 },
    },
    yAxis: { type: "value" },
    series: [
      {
        type: "bar",
        data: data.series.map((p) => p.value),
        itemStyle: { color: BAR_COLOR, borderRadius: [2, 2, 0, 0] },
      },
    ],
  };
}

export function buildOption(data: ChartData): EChartsCoreOption {
  switch (data.chart_type) {
    case "bar":
      return buildBarOption(data);
    case "pie":
      return buildPieOption(data);
    case "grouped_bar":
      return buildGroupedBarOption(data);
    default: {
      const exhaustive: never = data.chart_type;
      throw new Error(`Unknown chart_type: ${exhaustive}`);
    }
  }
}

export { echarts };
