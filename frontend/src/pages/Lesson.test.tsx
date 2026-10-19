import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import LessonPage from "./Lesson";
import { anonymous, mockApi, renderAt } from "@/test/utils";

afterEach(() => vi.unstubAllGlobals());

const lesson = {
  slug: "js-closures", title: "Closures: functions that remember", summary: "Inner functions capture variables.", minutes: 20,
  level: "beginner", tier: "free", tags: [], prerequisites: [], version: 2, updated_at: "2026-10-01T00:00:00Z", locked: false,
  breadcrumb: { track: { slug: "javascript-typescript", title: "JavaScript & TypeScript" }, course: "JavaScript Core", module: "Functions & Scope" },
  navigation: { prev: null, next: { slug: "js-event-loop", title: "The event loop" } }, progress: null, quiz_pass_threshold: 0.7,
  quiz: [{ id: "q1", prompt: "What does a closure capture?", options: ["Values", "Bindings"] }],
  exercises: [],
  content: { sections: {
    explanation: "A **closure** is a function bundled with its scope.", why_it_matters: "Hooks use them.", prerequisites: ["Functions"],
    mental_model: "A backpack.", architecture: null,
    code_examples: [{ title: "Counter", language: "javascript", runnable: true, code: "console.log(1)", expected_output: "1" }],
    real_world: "React hooks.", common_mistakes: [{ mistake: "Using var in loops", fix: "Use let" }], debugging: "Use the Scope panel.",
    performance_security: "Watch for leaks.", interview_questions: [{ q: "What is a closure?", a: "A function plus its scope." }],
    mini_challenge: { title: "Write once()", prompt: "Implement once.", exercise: "js-once" }, advanced_challenge: { title: "Memoize", prompt: "LRU memoize." },
    further_reading: [{ title: "MDN: Closures", url: "https://developer.mozilla.org" }],
  } },
};

describe("Lesson page", () => {
  it("renders every lesson part and asks anonymous users to sign in", async () => {
    mockApi({ ...anonymous, "GET /lessons/js-closures": lesson, "GET /sandbox/status": { available: true, mode: "sandbox", message: null } });
    renderAt("/lessons/js-closures", "/lessons/:slug", <LessonPage />);
    expect(await screen.findByRole("heading", { level: 1, name: lesson.title })).toBeInTheDocument();
    for (const h of ["The idea", "Why it matters", "Prerequisites", "Mental model", "Code you can run", "In the real world", "Common mistakes",
      "Debugging", "Performance & security", "Interview questions", "Challenges", "Further reading", "Check your understanding"]) {
      expect(screen.getByRole("heading", { level: 2, name: h })).toBeInTheDocument();
    }
    expect(screen.getByText("Expected output")).toBeInTheDocument();
    expect(screen.getAllByText(/Sign in/).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Open the exercise" })).toHaveAttribute("href", "/challenges/js-once");
  });

  it("shows an upgrade prompt for locked lessons", async () => {
    mockApi({ ...anonymous, "GET /lessons/js-closures": { ...lesson, locked: true, content: null, required_tier: "pro" } });
    renderAt("/lessons/js-closures", "/lessons/:slug", <LessonPage />);
    expect(await screen.findByText("This lesson is part of the Pro plan")).toBeInTheDocument();
  });

  it("shows the error message with its trace id", async () => {
    mockApi({ ...anonymous, "GET /lessons/js-closures": () => ({ status: 404, body: { error: { code: "not_found", message: "Lesson not found", trace_id: "t-1" } } }) });
    renderAt("/lessons/js-closures", "/lessons/:slug", <LessonPage />);
    expect(await screen.findByText("Lesson not found")).toBeInTheDocument();
    expect(screen.getByText("Trace id t-1")).toBeInTheDocument();
  });
});
