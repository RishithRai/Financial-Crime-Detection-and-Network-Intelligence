import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./browser",
  timeout: 120000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8000",
    viewport: { width: 1500, height: 1000 },
    launchOptions: {
      executablePath:
        process.env.CHROME_PATH ||
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    },
  },
  reporter: "list",
});
