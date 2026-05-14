import { expect, test } from "@playwright/test";

test.describe("ChartWidget e2e", () => {
  test("renders a real ECharts canvas with full chrome", async ({ page }) => {
    await page.goto("/test-chart");

    const populated = page.getByTestId("chart-populated");
    await expect(populated).toBeVisible();

    // Chrome
    await expect(populated.getByText("GRAPHIQUE")).toBeVisible();
    await expect(populated.getByText("Fréquence — type")).toBeVisible();
    await expect(populated.getByText(/rues_test/)).toBeVisible();
    await expect(populated.getByText(/100 features/)).toBeVisible();

    // Real canvas appears (proves ECharts mounted, not jsdom)
    const canvas = populated.locator("canvas");
    await expect(canvas).toBeVisible();
    // Give ResizeObserver a tick to size the canvas
    await page.waitForTimeout(200);
    const box = await canvas.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(0);
    expect(box?.height ?? 0).toBeGreaterThan(0);
  });

  test("renders empty state when series is empty", async ({ page }) => {
    await page.goto("/test-chart");

    const empty = page.getByTestId("chart-empty");
    await expect(empty).toBeVisible();
    await expect(empty.getByText(/Aucune donnée à grapher/i)).toBeVisible();
    await expect(empty.locator("canvas")).toHaveCount(0);
  });
});
