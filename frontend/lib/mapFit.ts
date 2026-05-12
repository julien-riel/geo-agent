import { DatasetMetaLite } from "@/lib/types";

type Bbox = [number, number, number, number];

function isUsableBbox(bbox: Bbox): boolean {
  const [minx, miny, maxx, maxy] = bbox;
  if (![minx, miny, maxx, maxy].every(Number.isFinite)) return false;
  // A dataset with no real geometry gets a [0,0,0,0] fallback bbox (see result_store);
  // fitting to a zero-area box would zoom the map all the way in.
  return minx !== maxx || miny !== maxy;
}

/**
 * Given the dataset ids that just became visible and the known datasets, return the bbox the map
 * should recenter on — the last-added layer's bbox, or null if there's nothing usable to fit.
 */
export function pickBboxToFit(addedIds: string[], datasets: DatasetMetaLite[]): Bbox | null {
  for (let i = addedIds.length - 1; i >= 0; i--) {
    const ds = datasets.find((d) => d.id === addedIds[i]);
    if (ds && isUsableBbox(ds.bbox)) return ds.bbox;
  }
  return null;
}
