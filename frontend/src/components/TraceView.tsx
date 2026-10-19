import { useState } from "react";
import type { Span } from "@/lib/types";
import { cn } from "@/lib/utils";

const KIND_COLOR: Record<string, string> = { step: "bg-signal", llm: "bg-llm", tool: "bg-tool" };
const KIND_TEXT: Record<string, string> = { step: "text-signal", llm: "text-llm", tool: "text-tool" };
const KIND_LABEL: Record<string, string> = { step: "Step", llm: "Model call", tool: "Tool" };

function fmt(ms: number) {
  if (ms < 1) return `${ms.toFixed(2)} ms`;
  if (ms < 1000) return `${ms.toFixed(ms < 10 ? 1 : 0)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

/**
 * Span waterfall: each row is a span positioned by its start time and sized by its duration.
 * `animate` replays the run once (used in the hero); otherwise it is static.
 */
export function TraceView({ spans, animate = false, compact = false, className }: { spans: Span[]; animate?: boolean; compact?: boolean; className?: string }) {
  const [open, setOpen] = useState<number | null>(null);
  const total = Math.max(0.001, ...spans.map((s) => s.start_ms + s.duration_ms));
  return (
    <div className={cn("text-sm", className)}>
      <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {(["step", "llm", "tool"] as const).filter((k) => spans.some((s) => s.kind === k)).map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className={cn("h-2 w-3 rounded-sm", KIND_COLOR[k])} /> {KIND_LABEL[k]}
          </span>
        ))}
        <span className="ml-auto tabular-nums">Total {fmt(total)}</span>
      </div>
      <ol className="space-y-1">
        {spans.map((s, i) => {
          const left = (s.start_ms / total) * 100;
          const width = Math.max(0.8, (s.duration_ms / total) * 100);
          const attrs = Object.entries(s.attributes ?? {});
          return (
            <li key={i}>
              <button
                type="button"
                disabled={compact || attrs.length === 0}
                onClick={() => setOpen(open === i ? null : i)}
                aria-expanded={open === i}
                className="grid w-full grid-cols-[minmax(0,7.5rem)_1fr_4rem] sm:grid-cols-[minmax(0,11rem)_1fr_4.5rem] items-center gap-3 rounded px-1.5 py-1 text-left hover:bg-panel-2 disabled:hover:bg-transparent"
              >
                <span className="truncate font-mono text-[12.5px]">
                  <span className={cn("mr-1", KIND_TEXT[s.kind] ?? "text-muted")}>{s.kind === "llm" ? "◆" : s.kind === "tool" ? "▲" : "●"}</span>
                  {s.name}
                </span>
                <span className="relative h-3.5 rounded-sm bg-panel-2">
                  <span
                    className={cn("absolute inset-y-0 rounded-sm", KIND_COLOR[s.kind] ?? "bg-muted", s.status === "error" && "bg-fail", animate && "span-bar")}
                    style={{ left: `${left}%`, width: `${width}%`, animationDelay: animate ? `${i * 380}ms` : undefined }}
                  />
                </span>
                <span className="text-right font-mono text-xs tabular-nums text-muted">{fmt(s.duration_ms)}</span>
              </button>
              {open === i && (
                <dl className="mb-2 ml-1.5 mt-1 grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 rounded border border-line bg-sunken p-2.5 font-mono text-xs">
                  {attrs.map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-faint">{k}</dt>
                      <dd className="break-all">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
