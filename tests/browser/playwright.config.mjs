import {defineConfig} from '@playwright/test';

const artifactRoot=process.env.PLAYWRIGHT_ARTIFACT_DIR||'/artifacts';

export default defineConfig({
  testDir: '.',
  testMatch: [/platform\.spec\.mjs/,/critical-journeys\.spec\.mjs/,/imovel-ui\.spec\.mjs/,/aitec-job\.spec\.mjs/],
  timeout: 120_000,
  expect: {timeout: 15_000},
  retries: 1,
  workers: 1,
  fullyParallel: false,
  outputDir: `${artifactRoot}/test-results`,
  reporter: [
    ['list'],
    ['json',{outputFile:`${artifactRoot}/playwright-results.json`}],
  ],
  use: {
    baseURL: process.env.BROWSER_BASE_URL||'http://127.0.0.1:8080',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    ignoreHTTPSErrors: true,
    actionTimeout: 15_000,
    navigationTimeout: 45_000,
  },
});
