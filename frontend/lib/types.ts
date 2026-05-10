import { z } from "zod";

export const DatasetMetaLite = z.object({
  id: z.string(),
  alias: z.string().nullable(),
  feature_count: z.number(),
  bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  layer: z.string().nullable(),
  operation: z.string(),
});
export type DatasetMetaLite = z.infer<typeof DatasetMetaLite>;

export const ToolError = z.object({
  code: z.string(),
  message: z.string(),
  suggestion: z.string().nullable().optional(),
});
export type ToolError = z.infer<typeof ToolError>;

export const AgentState = z.object({
  datasets: z.array(DatasetMetaLite.passthrough()),
  active_layers: z.array(z.string()),
  errors: z.array(ToolError),
});
export type AgentState = z.infer<typeof AgentState>;
