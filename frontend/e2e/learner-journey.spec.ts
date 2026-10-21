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
    for (const label of ["Learning Paths", "Interactive Coding Lab", "Daily Challenges", "AI Agent Library", "Real-World Projects", "Agent Builder Studio",
      "RAG Engineering Lab", "Prompt Engineering Lab", "LLM & SLM Lab", "Evaluations", "Interview Arena", "Portfolio", "AI Mentor", "Dashboard"]) {
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

  test("compares prompt versions and the hardened prompt resists injection", async ({ page }) => {
    await page.goto("/labs/prompts/injection-safe-summary");
    await page.getByRole("button", { name: /^Compare 2 variants/ }).click();
    await expect(page.getByText("Best:")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("row", { name: /^v2 best/ })).toContainText("100%");
  });

  test("answers from the handbook with citations and evaluates retrieval", async ({ page }) => {
    await page.goto("/labs/rag?dataset=northwind-handbook");
    await page.getByLabel("Question").fill("How many API requests per minute can a key send?");
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.getByText("Grounded", { exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/100 requests per minute/).first()).toBeVisible();
    await page.getByRole("tab", { name: "Evaluate" }).click();
    await page.getByRole("button", { name: "Run evaluation" }).click();
    await expect(page.getByText(/questions passed in/)).toBeVisible({ timeout: 30_000 });
  });

  test("builds a workflow from a template, pauses for approval and completes", async ({ page }) => {
    await page.goto("/builder");
    await page.getByRole("button", { name: /^Ticket triage with human approval/ }).click();
    await page.waitForURL(/\/builder\/[0-9a-f-]+$/);
    await expect(page.getByText("Valid", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await expect(page.getByText("awaiting approval")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("If approved, these will run next:")).toBeVisible();
    await page.getByRole("button", { name: "Approve", exact: true }).click();
    await expect(page.getByText("succeeded", { exact: true })).toBeVisible({ timeout: 15_000 });
  });

  test("takes a mock interview and gets rubric feedback", async ({ page }) => {
    await page.goto("/interviews/javascript");
    await page.getByRole("button", { name: "Start" }).click();
    await page.waitForURL(/\/interviews\/session\//);
    await page.getByLabel("Your answer").fill("It depends on the trade-off because each option has a cost; for example, a cache is faster but can serve stale data.");
    await page.getByRole("button", { name: "Submit answer" }).click();
    await expect(page.getByText("overall for this answer")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Concise answer")).toBeVisible();
  });
});
