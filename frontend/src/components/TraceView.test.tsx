import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TraceView } from "./TraceView";

const spans = [
  { kind: "step", name: "parse_diff", status: "ok", start_ms: 0, duration_ms: 0.4, attributes: {} },
  { kind: "llm", name: "review", status: "ok", start_ms: 0.5, duration_ms: 2.5, attributes: { model: "mock-1", input_tokens: 700 } },
  { kind: "tool", name: "search", status: "error", start_ms: 3, duration_ms: 1, attributes: { error: "ToolError: boom" } },
];

describe("TraceView", () => {
  it("renders a row per span with a legend and total", () => {
    render(<TraceView spans={spans} />);
    expect(screen.getByText("parse_diff")).toBeInTheDocument();
    expect(screen.getByText("Model call")).toBeInTheDocument();
    expect(screen.getByText("Tool")).toBeInTheDocument();
    expect(screen.getByText("Total 4.0 ms")).toBeInTheDocument();
  });

  it("expands span attributes on click", async () => {
    render(<TraceView spans={spans} />);
    await userEvent.click(screen.getByText("review"));
    expect(screen.getByText("input_tokens")).toBeInTheDocument();
    expect(screen.getByText("700")).toBeInTheDocument();
  });
});
