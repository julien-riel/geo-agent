import { expect, test } from "@playwright/test";

test("map and sidebar load", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible();
  // Check for either the sidebar title or datasets panel
  const geoAgent = page.locator("div").filter({ hasText: "Géo-agent" }).first();
  const datasets = page.locator("strong").filter({ hasText: "Datasets" }).first();
  const hasHeader = await geoAgent.isVisible().catch(() => false);
  const hasDatasets = await datasets.isVisible().catch(() => false);
  expect(hasHeader || hasDatasets).toBeTruthy();
  await expect(page.getByRole("button", { name: /Dessiner zone/i })).toBeVisible();
});
