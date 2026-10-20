import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

/**
 * E2E config (PLAN.md section 12). Launches the real app: FastAPI backend
 * serving the Next.js static export, with mandatory test isolation:
 *   LLM_MOCK=true, MARKET_DATA_SOURCE=simulator, a temp DATABASE_PATH, a
 *   dedicated PORT (8200, not the user's 8000). No Docker.
 */

const PORT = 8200;
const BACKEND_DIR = path.resolve(__dirname, "..", "backend");

// A unique DB file per run guarantees a freshly seeded state without deleting a
// file the backend has already opened and locked. Kept under test/.e2e (gitignored).
const E2E_DIR = path.resolve(__dirname, ".e2e");
fs.mkdirSync(E2E_DIR, { recursive: true });
const DB_PATH = path.join(E2E_DIR, `finally-${Date.now()}.db`);

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `uv run uvicorn app.main:app --host 127.0.0.1 --port ${PORT}`,
    cwd: BACKEND_DIR,
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      LLM_MOCK: "true",
      MARKET_DATA_SOURCE: "simulator",
      DATABASE_PATH: DB_PATH,
    },
  },
});
