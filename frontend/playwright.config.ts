import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  use: { baseURL: "http://localhost:3001", headless: true },
  webServer: {
    command: "PORT=3001 npm run dev",
    port: 3001,
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
  },
});
