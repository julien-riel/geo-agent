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

export const AgentState = z.object({
  datasets: z.array(DatasetMetaLite.passthrough()),
  current_drawing: z.any().nullable(),
  active_layers: z.array(z.string()),
  last_error: z.string().nullable(),
});
export type AgentState = z.infer<typeof AgentState>;
