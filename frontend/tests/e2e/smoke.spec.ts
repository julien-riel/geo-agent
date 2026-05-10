import { expect, test } from "@playwright/test";

test("draw zone creates a dataset card and map layer", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible();
  await expect(page.getByRole("button", { name: /Dessiner zone/i })).toBeVisible();

  // Stub the backend POST so the e2e test doesn't depend on a running backend.
  await page.route("**/api/datasets/drawing", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "result_001",
        alias: "zone_1",
        feature_count: 1,
        bbox: [-73.6, 45.5, -73.55, 45.55],
        layer: null,
        operation: "user_drawing",
      }),
    });
  });

  // The CopilotKit sidebar opens by default and overlaps the "Dessiner zone"
  // button. Close it via JS to avoid pointer-interception issues.
  await page.evaluate(() => {
    const btn = document.querySelector<HTMLElement>(
      'button[aria-label="Close Chat"], button[aria-label="Close"]'
    );
    btn?.click();
  });
  await page.waitForTimeout(300);

  await page.getByRole("button", { name: /Dessiner zone/i }).click();

  // Wait for terra-draw to activate: it sets cursor to "crosshair" on the canvas
  // once its useEffect has registered all pointer listeners.
  await page.waitForFunction(() => {
    const canvas = document.querySelector<HTMLCanvasElement>("canvas.maplibregl-canvas");
    return canvas ? getComputedStyle(canvas).cursor === "crosshair" : false;
  }, { timeout: 5000 });

  // Terra-draw registers pointerdown/pointerup listeners on the MapLibre canvas.
  // page.mouse.click() doesn't set isPrimary=true on PointerEvents, so terra-draw
  // ignores those clicks. We dispatch PointerEvents directly via evaluate instead.
  await page.evaluate(() => {
    const canvasOrNull = document.querySelector<HTMLCanvasElement>("canvas.maplibregl-canvas");
    if (!canvasOrNull) throw new Error("MapLibre canvas not found");
    const canvas: HTMLCanvasElement = canvasOrNull;

    function pclick(x: number, y: number) {
      const opts: PointerEventInit = {
        clientX: x, clientY: y,
        bubbles: true, cancelable: true,
        pointerId: 1, pointerType: "mouse",
        isPrimary: true,
        button: 0, buttons: 1,
      };
      canvas.dispatchEvent(new PointerEvent("pointermove", opts));
      canvas.dispatchEvent(new PointerEvent("pointerdown", opts));
      canvas.dispatchEvent(new PointerEvent("pointerup", opts));
    }

    // Draw a rectangle: 4 corner points.
    pclick(300, 250);
    pclick(500, 250);
    pclick(500, 400);
    pclick(300, 400);

    // Terra-draw polygon mode finishes on Enter (keyEvents.finish = "Enter").
    canvas.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    canvas.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
  });

  // Assert the new dataset card shows up and is checked.
  await expect(page.getByText("zone_1", { exact: false })).toBeVisible({ timeout: 5000 });
  const checkbox = page.getByRole("checkbox", { name: /zone_1/i });
  await expect(checkbox).toBeChecked();
});

test("clicking Nouveau resets chat and dataset panel", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("canvas")).toBeVisible();

  await page.route("**/api/datasets/drawing", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "result_001",
        alias: "zone_1",
        feature_count: 1,
        bbox: [-73.6, 45.5, -73.55, 45.55],
        layer: null,
        operation: "user_drawing",
      }),
    });
  });

  // Close the chat sidebar so we can interact with the canvas underneath.
  await page.evaluate(() => {
    const closeBtn = document.querySelector('button[aria-label="Close Chat"]') as HTMLElement | null;
    closeBtn?.click();
  });
  await page.getByRole("button", { name: /Dessiner zone/i }).click();
  await page.waitForFunction(() => {
    const c = document.querySelector<HTMLCanvasElement>("canvas.maplibregl-canvas");
    return c ? getComputedStyle(c).cursor === "crosshair" : false;
  }, { timeout: 5000 });
  await page.evaluate(() => {
    const canvasOrNull = document.querySelector<HTMLCanvasElement>("canvas.maplibregl-canvas");
    if (!canvasOrNull) throw new Error("MapLibre canvas not found");
    const canvas: HTMLCanvasElement = canvasOrNull;
    const opts = (x: number, y: number): PointerEventInit => ({
      clientX: x, clientY: y, bubbles: true, cancelable: true,
      pointerId: 1, pointerType: "mouse", isPrimary: true, button: 0, buttons: 1,
    });
    function pclick(x: number, y: number) {
      canvas.dispatchEvent(new PointerEvent("pointermove", opts(x, y)));
      canvas.dispatchEvent(new PointerEvent("pointerdown", opts(x, y)));
      canvas.dispatchEvent(new PointerEvent("pointerup", opts(x, y)));
    }
    pclick(300, 250); pclick(500, 250); pclick(500, 400); pclick(300, 400);
    canvas.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    canvas.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
  });

  // Pre-condition: dataset card is present.
  await expect(page.getByText("zone_1", { exact: false })).toBeVisible({ timeout: 5000 });

  // Re-open the chat sidebar.
  await page.evaluate(() => {
    const open = document.querySelector('button[aria-label="Open Chat"]') as HTMLElement | null;
    open?.click();
  });

  // Click the "Nouveau" button via JS to avoid cpk-web-inspector pointer interception.
  // This triggers window.location.reload(), so we need to wait for navigation.
  await Promise.all([
    page.waitForLoadState("domcontentloaded"),
    page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll("button")).find(
        (b) => /Nouvelle conversation/i.test(b.getAttribute("aria-label") ?? b.textContent ?? "")
      ) as HTMLElement | undefined;
      if (!btn) throw new Error("Nouvelle conversation button not found");
      btn.click();
    }),
  ]);

  // Post-conditions: dataset panel is empty AND no more zone_1 card.
  await expect(page.getByText("Aucun dataset", { exact: false })).toBeVisible({ timeout: 8000 });
  await expect(page.getByText("zone_1", { exact: false })).toHaveCount(0);
});
