import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { anonymous, mockApi, renderAt } from "@/test/utils";
import ModelsLab, { estimateMemory } from "./labs/ModelsLab";
import RagLab from "./labs/RagLab";
import { EvaluationsList } from "./Evaluations";
import { InterviewSession } from "./Interviews";
import Mentor from "./Mentor";

afterEach(() => vi.unstubAllGlobals());

const me = {
  "GET /auth/me": { id: "u1", email: "l@example.com", email_verified: true, roles: ["learner"], plan: "free", created_at: "2026-10-01",
    profile: { display_name: "Lee", bio: "", avatar_url: null, experience_level: "beginner", goals: [], mentor_opt_in: false, public_portfolio: false } },
};

describe("LLM & SLM lab", () => {
  it("estimates memory: weights scale with precision and KV cache with context", () => {
    const a = estimateMemory(8, 16, 8192, 1);
    const b = estimateMemory(8, 4.5, 8192, 1);
    expect(a.weights).toBeCloseTo(16, 5);
    expect(b.weights).toBeCloseTo(4.5, 5);
    expect(estimateMemory(8, 4.5, 32768, 1).kv).toBeCloseTo(b.kv * 4, 5);
    expect(a.full).toBe(128);
  });

  it("ranks models for private data and rules out hosted-only ones", async () => {
    mockApi({
      ...anonymous,
      "GET /llm-lab/catalog": { version_note: "Reviewed", techniques: [], models: [
        { key: "api-frontier", name: "Frontier hosted", family: "x", params_b: null, context_k: 200, license: "Proprietary", open_weights: false, class: "api", strengths: ["Reasoning"], weaknesses: [] },
        { key: "llama-3.1-8b", name: "Llama 3.1 8B", family: "Meta", params_b: 8, context_k: 128, license: "Llama", open_weights: true, class: "slm", strengths: ["Small"], weaknesses: [] },
      ] },
      "GET /llm-lab/providers": { server_provider: "mock", server_model: "simulator-1", local_model: false, your_plan: "free", you_get: "simulator", how_to_run_locally: "" },
    });
    renderAt("/labs/models", "/labs/models", <ModelsLab />);
    fireEvent.click(await screen.findByLabelText("Data can't leave our environment"));
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Llama 3.1 8B");
    expect(screen.getByText("Data must stay in your environment, and this is hosted only")).toBeInTheDocument();
  });
});

describe("RAG lab", () => {
  it("shows the pipeline stages, scored passages and a cited answer", async () => {
    const { calls } = mockApi({
      ...me,
      "GET /rag/options": { chunkers: [{ key: "markdown", label: "Structure-aware" }], strategies: [{ key: "hybrid", label: "Hybrid (RRF)" }], embedders: [{ key: "hashing-384", label: "Hashing", available: true }],
        defaults: { chunker: "markdown", size: 120, overlap: 20, embedder: "hashing-384" }, default_prompt: { system: "Answer from passages", user: "{{passages}} {{question}}" }, your_groups: ["everyone"] },
      "GET /rag/datasets": { items: [{ id: "1", slug: "northwind-handbook", name: "Northwind", description: "", mine: false, documents: 1, questions: 0 }] },
      "GET /rag/datasets/northwind-handbook": { id: "1", slug: "northwind-handbook", name: "Northwind", description: "Handbook", mine: false, documents: [], questions: [], indexes: [], your_groups: ["everyone"] },
      "POST /rag/query": { retrieved: [{ rank: 1, chunk_id: "c1", document: "Public API Rate Limits", source: "api-rate-limits", heading: "Limits", text: "100 requests per minute", tokens: 5, scores: { vector: 0.4, keyword: 15.1, fused: 0.03, rerank: 0.7 }, score: 0.7 }],
        index: { chunks: 32, backend: "pgvector", build_ms: 3 }, stages: [{ stage: "retrieve (hybrid)", ms: 1 }], latency_ms: 4, mode: "mock", provider_label: "Simulator",
        generation: { answer: "100 requests per minute [1]", citations: [{ n: 1, document: "Public API Rate Limits", source: "api-rate-limits", heading: "Limits", quote: "100 requests per minute" }], invalid_citations: [], grounded: true, says_unknown: false, input_tokens: 10, output_tokens: 5, latency_ms: 1, cost_usd: 0, prompt: { system: "s", user: "u" } } },
    });
    renderAt("/labs/rag", "/labs/rag", <RagLab />);
    fireEvent.change(await screen.findByLabelText("Question"), { target: { value: "How many requests per minute?" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Grounded")).toBeInTheDocument();
    expect(screen.getByText("rerank 0.700")).toBeInTheDocument();
    expect(screen.getByText("retrieve (hybrid)")).toBeInTheDocument();
    const body = JSON.parse(String(calls.find((c) => c.path === "/rag/query")!.init!.body));
    expect(body).toMatchObject({ dataset: "northwind-handbook", strategy: "hybrid", top_k: 4, rerank: true });
  });
});

describe("Evaluations", () => {
  it("only lets you compare two evaluations of the same kind", async () => {
    mockApi({
      ...me,
      "GET /evaluations": { items: [
        { id: "a", name: "RAG run A", target_type: "rag", summary: { kind: "rag_eval", metrics: { hit_rate: 0.75 } }, created_at: "2026-10-20" },
        { id: "b", name: "RAG run B", target_type: "rag", summary: { kind: "rag_eval", metrics: { hit_rate: 1 } }, created_at: "2026-10-21" },
        { id: "c", name: "Prompt cmp", target_type: "prompt", summary: { kind: "prompt_compare", best: "v2", variants: [{ label: "v2", pass_rate: 1 }] }, created_at: "2026-10-21" },
      ] },
    });
    renderAt("/evaluations", "/evaluations", <EvaluationsList />);
    fireEvent.click(await screen.findByLabelText("Select RAG run A"));
    expect(screen.getByLabelText("Select Prompt cmp")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Compare selected" })).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Select RAG run B"));
    expect(screen.getByRole("button", { name: "Compare selected" })).toBeEnabled();
    expect(screen.getByText("75%")).toBeInTheDocument();
  });
});

describe("Interview session", () => {
  it("hides the reference until you answer, then shows rubric scores", async () => {
    let answered = false;
    const q = { id: "q1", track: "javascript", difficulty: "beginner", prompt: "What is the event loop?" };
    const full = { ...q, concise_answer: "It runs tasks one at a time.", explanation: "", example: "", follow_ups: [], common_mistakes: [], key_points: ["microtask"] };
    mockApi({
      ...me,
      "GET /interviews/tracks": { items: [{ slug: "javascript", title: "JavaScript", questions: 4 }] },
      "GET /interviews/sessions/s1": () => ({ body: { id: "s1", track: "javascript", status: "in_progress", scorer: "rubric", overall: null, summary: null, disclaimer: "Practice feedback, not a prediction.",
        items: [{ question: answered ? full : q, answer: answered ? { text: "Microtasks first because...", scores: { technical_accuracy: 0.9, reasoning: 0.6, tradeoffs: 0.3, communication: 0.8 }, feedback: { technical_accuracy: "Covered: microtask." }, overall: 0.72 } : null }] } }),
      "POST /interviews/sessions/s1/answers": () => { answered = true; return { body: {} }; },
    });
    renderAt("/interviews/session/s1", "/interviews/session/:id", <InterviewSession />);
    expect(await screen.findByText("What is the event loop?")).toBeInTheDocument();
    expect(screen.queryByText("It runs tasks one at a time.")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Your answer"), { target: { value: "Microtasks first because the loop drains them" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit answer" }));
    expect(await screen.findByText("It runs tasks one at a time.")).toBeInTheDocument();
    expect(screen.getByText("72%")).toBeInTheDocument();
    expect(screen.getByText("Covered: microtask.")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "JavaScript" })).toBeInTheDocument();
  });
});

describe("AI mentor", () => {
  it("is opt-in and explains what it reads before turning on", async () => {
    const { calls } = mockApi({
      ...me,
      "GET /mentor/status": { opted_in: false, stored_messages: 0, assessment: null, privacy: "The mentor reads lesson content and your own attempts." },
      "PATCH /me/profile": me["GET /auth/me"],
    });
    renderAt("/mentor", "/mentor", <Mentor />);
    expect(await screen.findByText("The mentor reads lesson content and your own attempts.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Message the mentor")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Turn on the mentor" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH" && c.path === "/me/profile" && String(c.init?.body).includes('"mentor_opt_in":true'))).toBe(true));
  });
});
