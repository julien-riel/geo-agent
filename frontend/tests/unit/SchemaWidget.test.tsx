import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SchemaWidget } from "@/components/Widgets/SchemaWidget";

const DATA = {
  id: "result_002",
  alias: "routes",
  attribute_schema: { id_chaussee: "number", nom_voie: "string", en_service: "boolean" },
};

const SAMPLE_GJ = {
  type: "FeatureCollection",
  features: [{ type: "Feature", geometry: { type: "Point", coordinates: [0, 0] }, properties: { id_chaussee: 8421, nom_voie: "Rue X", en_service: true } }],
};

const SAMPLE_STATS = {
  attribute: "id_chaussee",
  type: "number",
  non_null_count: 95,
  null_count: 5,
  distinct_count: 87,
  min: 1,
  max: 999,
};

describe("SchemaWidget", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/api/datasets/result_002")) {
          return new Response(JSON.stringify(SAMPLE_GJ), { status: 200 });
        }
        if (url.includes("/attributes/id_chaussee/stats")) {
          return new Response(JSON.stringify(SAMPLE_STATS), { status: 200 });
        }
        return new Response("not found", { status: 404 });
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders one row per attribute with type chips", async () => {
    render(<SchemaWidget data={DATA} datasetId="result_002" />);
    expect(screen.getByText("id_chaussee")).toBeInTheDocument();
    expect(screen.getByText("nom_voie")).toBeInTheDocument();
    expect(screen.getByText("en_service")).toBeInTheDocument();
    expect(screen.getAllByText(/number|string|boolean/)).toHaveLength(3);
  });

  it("populates the example column from the first feature once fetched", async () => {
    render(<SchemaWidget data={DATA} datasetId="result_002" />);
    await waitFor(() => {
      expect(screen.getByText("8421")).toBeInTheDocument();
      expect(screen.getByText('"Rue X"')).toBeInTheDocument();
      expect(screen.getByText("true")).toBeInTheDocument();
    });
  });

  it("expands a row and triggers the stats fetch", async () => {
    render(<SchemaWidget data={DATA} datasetId="result_002" />);
    fireEvent.click(screen.getByText("id_chaussee"));
    await waitFor(() => {
      expect(screen.getByText(/Distinctes/)).toBeInTheDocument();
      expect(screen.getByText("87")).toBeInTheDocument();   // distinct_count
      expect(screen.getByText("999")).toBeInTheDocument(); // max
    });
  });
});
