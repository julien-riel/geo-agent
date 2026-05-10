"use client";

interface Props {
  data: { attribute_schema: Record<string, string> };
  datasetId: string;
}

export function SchemaWidget({ data }: Props) {
  return (
    <div>
      {Object.keys(data.attribute_schema).map((k) => (
        <div key={k}>{k}</div>
      ))}
    </div>
  );
}
