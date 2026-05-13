import { test, expect } from "@playwright/test";

test.describe("tool-feedback", () => {
  test("pill appears, dataset card lands during turn, no stuck Chargement", async ({ page }) => {
    await page.goto("/");
    // Wait for the sidebar to render
    await expect(page.locator(".copilotKitInput textarea")).toBeVisible({ timeout: 10000 });

    // Draw a small zone in the middle of the viewport
    await page.getByRole("button", { name: /Dessiner zone/i }).click();
    const map = page.locator("canvas").first();
    const box = await map.boundingBox();
    if (!box) throw new Error("no map canvas");
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await page.mouse.click(cx - 60, cy - 60);
    await page.mouse.click(cx + 60, cy - 60);
    await page.mouse.click(cx + 60, cy + 60);
    await page.mouse.click(cx - 60, cy + 60);
    await page.mouse.dblclick(cx - 60, cy - 60);

    // Send a chat message
    await page.locator(".copilotKitInput textarea").fill("Trouve les chaussées dans cette zone");
    await page.keyboard.press("Enter");

    // Pill should appear within 3s
    await expect(
      page.getByRole("status").filter({ hasText: /Sélection|Filtrage|Inspection|Liste|Agrégation/i })
    ).toBeVisible({ timeout: 3000 });

    // At least one dataset card should land in the chat before 30s
    await expect(page.locator("text=DATASET").first()).toBeVisible({ timeout: 30000 });

    // Wait 5s after no more activity, then assert "Chargement…" is absent
    await page.waitForTimeout(5000);
    const stuck = await page.evaluate(() => document.body.innerText.includes("Chargement"));
    expect(stuck).toBe(false);
  });
});
