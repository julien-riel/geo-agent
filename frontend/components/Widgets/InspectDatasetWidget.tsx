"use client";

import type { InspectResult } from "@/lib/types";
import { FeatureListWidget } from "./FeatureListWidget";
import { FeatureWidget } from "./FeatureWidget";
import { SchemaWidget } from "./SchemaWidget";

export function InspectDatasetWidget({ data }: { data: InspectResult }) {
  if (data.view === "schema") {
    return (
      <SchemaWidget
        data={{ id: data.dataset_id, alias: data.alias, attribute_schema: data.attribute_schema }}
        datasetId={data.dataset_id}
        sample={data.sample}
      />
    );
  }
  if (data.view === "feature") {
    return <FeatureWidget data={data} />;
  }
  return <FeatureListWidget data={data} />;
}
