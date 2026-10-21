import { expect, test, type Page } from "@playwright/test";

const EMAIL = process.env.E2E_EMAIL ?? "learner@example.com";
const PASSWORD = process.env.E2E_PASSWORD ?? "ChangeMe-Learner-123!";

// Current Chrome returns a Promise from window.scrollTo (older Chromium returns undefined).
// Emulate it everywhere so effects that accidentally return its result are caught.
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const original = window.scrollTo.bind(window) as (...a: unknown[]) => void;
    (window as unknown as { scrollTo: (...a: unknown[]) => Promise<void> }).scrollTo = (...args: unknown[]) => {
      original(...args);
      return Promise.resolve();
    };
  });
  page.on("pageerror", (err) => { throw err; });
});

async function signIn(page: Page) {
  await page.goto("/login");
  await page.fill("#email", EMAIL);
  await page.fill("#password", PASSWORD);
  await page.click("button[type=submit]");
  await page.waitForURL("**/dashboard");
}

test("landing page explains the product and replays a real agent trace", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Learn to Build AI Systems That Actually Work.");
  await expect(page.getByRole("button", { name: "Explore 100+ AI Agents" })).toBeVisible();
  await expect(page.getByText("parse_diff")).toBeVisible();
});

test.describe("signed-in learner", () => {
  test.beforeEach(async ({ page }) => signIn(page));

  test("navigates between pages with in-app links without crashing", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    for (const label of ["Learning Paths", "Interactive Coding Lab", "Daily Challenges", "AI Agent Library", "Real-World Projects", "Dashboard"]) {
      await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: label }).click();
      await expect(page.locator("main h1").first()).toBeVisible();
    }
    await page.getByRole("link", { name: "Continue lesson" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "The idea" })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("runs a lesson example in the sandbox", async ({ page }) => {
    await page.goto("/lessons/js-closures");
    await page.getByRole("button", { name: "Run" }).first().click();
    await expect(page.getByText("Matches expected output").first()).toBeVisible({ timeout: 15_000 });
  });

  test("solves a code challenge graded against hidden tests", async ({ page }) => {
    await page.goto("/challenges/py-two-sum");
    const editor = page.locator(".monaco-editor").first();
    await editor.click();
    await page.keyboard.press("ControlOrMeta+A");
    await page.keyboard.press("Delete");
    // single line: Monaco auto-indents multi-line inserted text
    await page.keyboard.insertText(`def two_sum(nums, target): return next([i, j] for j in range(len(nums)) for i in range(j) if nums[i] + nums[j] == target)  # ${Date.now()}`);
    await page.getByRole("button", { name: /Submit and run tests/ }).click();
    await expect(page.getByText("4/4 tests")).toBeVisible({ timeout: 20_000 });
  });

  test("runs an agent and approves its side effect", async ({ page }) => {
    await page.goto("/agents/bug-triage-agent");
    await page.getByRole("tab", { name: "Run it" }).click();
    await page.getByRole("button", { name: "Run agent" }).click();
    const approve = page.getByRole("button", { name: "Approve and apply" });
    await expect(approve).toBeVisible({ timeout: 20_000 });
    await approve.click();
    await expect(page.getByText("Action approved and applied")).toBeVisible();
  });

  test("passes a quiz", async ({ page }) => {
    await page.goto("/lessons/js-closures");
    await page.getByText("The variables (bindings) themselves").click();
    await page.getByText("have independent counts").click();
    await page.getByRole("button", { name: "Check answers" }).click();
    await expect(page.getByText(/100% - passed/)).toBeVisible();
  });
});
