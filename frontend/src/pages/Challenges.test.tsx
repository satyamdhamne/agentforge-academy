import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import Challenges from "./Challenges";
import { anonymous, mockApi, renderAt } from "@/test/utils";

afterEach(() => vi.unstubAllGlobals());

const card = (o: object) => ({ slug: "a", title: "A", kind: "code", category: "coding", difficulty: "beginner", language: "python", points: 10, tier: "free", tags: [], time_limit_minutes: null, is_weekly_project: false, solved: false, locked: false, ...o });

describe("Challenges page", () => {
  it("lists challenges with kind, time limit and the daily challenge", async () => {
    mockApi({
      ...anonymous,
      "GET /challenges/daily": card({ slug: "d", title: "Daily one", date: "2026-10-19" }),
      "GET /challenges": { items: [card({ slug: "x", title: "Two-sum" }), card({ slug: "y", title: "Merge intervals", category: "interview", time_limit_minutes: 20 }), card({ slug: "z", title: "Design RAG", kind: "manual_review", language: null })], total: 3, categories: ["coding", "interview"] },
    });
    renderAt("/challenges", "/challenges", <Challenges />);
    expect(await screen.findByText("Two-sum")).toBeInTheDocument();
    expect(screen.getByText("Daily one")).toBeInTheDocument();
    expect(screen.getByText("20 min")).toBeInTheDocument();
    expect(screen.getByText("Reviewed by a person")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Timed interview" })).toBeInTheDocument();
  });
});
