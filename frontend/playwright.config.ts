import { defineConfig } from "@playwright/test";
import path from "node:path";
import { randomUUID } from "node:crypto";

const root = path.resolve(__dirname, "..");
const python = process.env.SMARTARCHIVE_TEST_PYTHON || path.join(root, ".venv", "Scripts", "python.exe");
const storage = path.join(root, ".tools", "e2e-storage", randomUUID());
export default defineConfig({
  testDir: "./tests", fullyParallel: false, workers: 1, timeout: 60_000,
  reporter: "list", outputDir: "test-results",
  use: { baseURL: "http://127.0.0.1:3001", headless: true,
    channel: process.env.SMARTARCHIVE_BROWSER_CHANNEL || "msedge", trace: "retain-on-failure" },
  webServer: [
    { command: `"${python}" -m uvicorn smartarchive.api.app:app --app-dir src --host 127.0.0.1 --port 8001`,
      cwd: root, url: "http://127.0.0.1:8001/api/health", reuseExistingServer: false, timeout: 60_000,
      env: { SMARTARCHIVE_STORAGE_DIR: storage, SMARTARCHIVE_CORS_ORIGINS: "http://127.0.0.1:3001" } },
    { command: "node node_modules/next/dist/bin/next dev --webpack --hostname 127.0.0.1 --port 3001",
      url: "http://127.0.0.1:3001", reuseExistingServer: false, timeout: 120_000,
      env: { NEXT_PUBLIC_API_URL: "http://127.0.0.1:8001", SMARTARCHIVE_NEXT_DIR: ".next-e2e", NEXT_TELEMETRY_DISABLED: "1" } },
  ],
});
