import { expect, test } from "@playwright/test";

const FAKE_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { id_chaussee: 8421, nom_voie: "Rue Saint-Denis", longueur_m: 147.3, en_service: true },
      geometry: { type: "LineString", coordinates: [[-73.58, 45.52], [-73.57, 45.525], [-73.56, 45.53]] },
    },
  ],
};

const FAKE_META = {
  id: "result_001",
  alias: "test_road",
  feature_count: 1,
  bbox: [-73.58, 45.52, -73.56, 45.53],
  source: { type: "wfs", layer: "geobase:chaussee", filter_summary: "" },
  attribute_schema: { id_chaussee: "number", nom_voie: "string", longueur_m: "number", en_service: "boolean" },
  lineage: { parent_ids: [], operation: "select_features", params: {} },
  created_at: "2026-05-10T12:00:00Z",
  size_bytes: 256,
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/datasets", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([FAKE_META]) }));
  await page.route("**/api/datasets/result_001", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FAKE_GEOJSON) }));
});

test("clicking a feature opens popup, then drawer with properties", async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible();

  // Close the chat sidebar so it doesn't intercept clicks.
  await page.evaluate(() => {
    const btn = document.querySelector<HTMLElement>('button[aria-label="Close Chat"]');
    btn?.click();
  });
  await page.waitForTimeout(300);

  // Wait for the dataset panel to hydrate (the fake /api/datasets stub returns test_road).
  await page.waitForFunction(
    () => Array.from(document.querySelectorAll("label")).some((l) => l.textContent?.includes("test_road")),
    { timeout: 8000 }
  );

  // Toggle the dataset on so it becomes an active layer.
  // Use JS dispatch to bypass the Next.js dev overlay <nextjs-portal> pointer interception.
  await page.evaluate(() => {
    const checkboxes = Array.from(document.querySelectorAll<HTMLInputElement>("input[type='checkbox']"));
    // Find the one associated with test_road (look at sibling/parent text)
    const cb = checkboxes.find((c) => {
      const label = c.closest("label") ?? c.parentElement;
      return label?.textContent?.toLowerCase().includes("test_road");
    });
    if (!cb) throw new Error("test_road checkbox not found");
    if (!cb.checked) {
      cb.click();
    }
  });

  // Wait for both the test helper (SelectedFeatureProvider) and the map (MapView) to be ready.
  await page.waitForFunction(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    () => typeof (window as any).__testSetSelected === "function" && Boolean((window as any).__map),
    { timeout: 20000 }
  );

  // Simulate a feature click by directly calling setSelected via the test hook.
  // This bypasses MapLibre's pixel hit-test (which is unreliable in headless WebGL)
  // while still exercising the full popup → drawer React flow.
  await page.evaluate(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).__testSetSelected({
      datasetId: "result_001",
      index: 0,
      feature: {
        type: "Feature",
        properties: { id_chaussee: 8421, nom_voie: "Rue Saint-Denis", longueur_m: 147.3, en_service: true },
        geometry: { type: "LineString", coordinates: [[-73.58, 45.52], [-73.57, 45.525], [-73.56, 45.53]] },
      },
      lngLat: [-73.57, 45.525],
    });
  });

  // Wait for the MapLibre popup to appear in the DOM (it's a portal outside the React tree).
  await page.waitForSelector(".maplibregl-popup", { timeout: 5000 });
  // Popup should show the title.
  await expect(page.locator(".maplibregl-popup").getByText("Rue Saint-Denis", { exact: false })).toBeVisible({ timeout: 5000 });

  // Click the "Détails →" link inside the popup.
  await page.getByRole("button", { name: /Détails/i }).click();

  // Drawer assertions.
  // Geometry type badge should be visible in the drawer.
  await expect(page.getByText("LineString", { exact: false })).toBeVisible({ timeout: 5000 });
  // Property key appears as a table cell in the drawer (exact match avoids popup stats text).
  await expect(page.getByRole("cell", { name: "id_chaussee" })).toBeVisible({ timeout: 5000 });
  // "Fit map" button inside the drawer.
  await expect(page.getByRole("button", { name: /Cadrer la carte/i })).toBeVisible({ timeout: 5000 });
});
