import { describe, expect, it } from "vitest";

import { pickBboxToFit } from "@/lib/mapFit";
import { DatasetMetaLite } from "@/lib/types";

function ds(id: string, bbox: [number, number, number, number]): DatasetMetaLite {
  return { id, alias: null, feature_count: 1, bbox, layer: null, operation: "select_features", parent_ids: [] };
}

const PARC = ds("result_001", [-73.57, 45.53, -73.56, 45.54]);
const ZONE = ds("result_002", [-73.6, 45.5, -73.55, 45.55]);

describe("pickBboxToFit", () => {
  it("returns null when nothing was added", () => {
    expect(pickBboxToFit([], [PARC, ZONE])).toBeNull();
  });

  it("returns the added layer's bbox", () => {
    expect(pickBboxToFit(["result_001"], [PARC, ZONE])).toEqual([-73.57, 45.53, -73.56, 45.54]);
  });

  it("returns the last added layer's bbox when several were added at once", () => {
    expect(pickBboxToFit(["result_002", "result_001"], [PARC, ZONE])).toEqual([-73.57, 45.53, -73.56, 45.54]);
  });

  it("returns null when the added id is not among the known datasets", () => {
    expect(pickBboxToFit(["result_999"], [PARC, ZONE])).toBeNull();
  });

  it("returns null for a degenerate (zero-area) bbox", () => {
    expect(pickBboxToFit(["result_003"], [ds("result_003", [0, 0, 0, 0])])).toBeNull();
  });

  it("returns null for a non-finite bbox", () => {
    expect(pickBboxToFit(["result_004"], [ds("result_004", [NaN, 0, 1, 1])])).toBeNull();
  });
});
