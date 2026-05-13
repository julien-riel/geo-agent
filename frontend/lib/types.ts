import { z } from "zod";

export const DatasetMetaLite = z.object({
  id: z.string(),
  alias: z.string().nullable(),
  feature_count: z.number(),
  bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  layer: z.string().nullable(),
  operation: z.string(),
  parent_ids: z.array(z.string()).default([]),
  tool_call_id: z.string().nullable().optional(),
});
export type DatasetMetaLite = z.infer<typeof DatasetMetaLite>;

export const ToolError = z.object({
  code: z.string(),
  message: z.string(),
  suggestion: z.string().nullable().optional(),
});
export type ToolError = z.infer<typeof ToolError>;

export const ToolEvent = z.object({
  id: z.string(),
  tool_call_id: z.string(),
  tool: z.string(),
  args_summary: z.string(),
  args_raw: z.record(z.string(), z.unknown()),
  started_at: z.number(),
  ended_at: z.number().nullable(),
  duration_ms: z.number().nullable(),
  status: z.enum(["running", "ok", "error"]),
  result_summary: z.string().optional(),
  error: z
    .object({
      code: z.string(),
      message: z.string(),
    })
    .optional(),
});
export type ToolEvent = z.infer<typeof ToolEvent>;

export const InspectSchemaResult = z.object({
  view: z.literal("schema"),
  dataset_id: z.string(),
  alias: z.string().nullable(),
  attribute_schema: z.record(z.string(), z.string()),
  sample: z.record(z.string(), z.unknown()),
});

export const InspectFeatureRow = z.object({
  index: z.number(),
  properties: z.record(z.string(), z.unknown()),
  geometry_type: z.string().nullable(),
});

export const InspectFeaturesResult = z.object({
  view: z.literal("features"),
  dataset_id: z.string(),
  alias: z.string().nullable(),
  total: z.number(),
  features: z.array(InspectFeatureRow),
});

export const InspectFeatureResult = z.object({
  view: z.literal("feature"),
  dataset_id: z.string(),
  alias: z.string().nullable(),
  index: z.number(),
  properties: z.record(z.string(), z.unknown()),
  geometry_type: z.string().nullable(),
  vertex_count: z.number(),
});

export const InspectResult = z.discriminatedUnion("view", [InspectSchemaResult, InspectFeaturesResult, InspectFeatureResult]);
export type InspectResult = z.infer<typeof InspectResult>;

export const AgentState = z.object({
  datasets: z.array(DatasetMetaLite.passthrough()),
  active_layers: z.array(z.string()),
  errors: z.array(ToolError),
  inspections: z.array(InspectResult).optional(),
  tool_events: z.array(ToolEvent).default([]),
});
export type AgentState = z.infer<typeof AgentState>;
