import { defineConfig } from "@playwright/test";

const port = Number(process.env.PORT ?? 3000);

export default defineConfig({
  testDir: "./tests/e2e",
  use: { baseURL: `http://localhost:${port}`, headless: true },
  webServer: {
    command: `PORT=${port} npm run dev`,
    port,
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
  },
});
