import { CheckCircle2, XCircle } from "lucide-react";
import { Badge } from "./ui/badge";
import { cn } from "@/lib/utils";

export interface CheckResult { type: string; value?: unknown; passed: boolean; detail?: string; label: string }

export function ModeBadge({ mode, label }: { mode?: string | null; label?: string | null }) {
  if (!mode) return null;
  return (
    <Badge tone={mode === "live" ? "llm" : "neutral"} title={label ?? undefined}>
      {mode === "live" ? "Live model" : "Simulator"}
    </Badge>
  );
}

export function CheckList({ results, className }: { results: CheckResult[]; className?: string }) {
  if (!results.length) return null;
  return (
    <ul className={cn("space-y-1 text-sm", className)}>
      {results.map((r, i) => (
        <li key={i} className="flex gap-2">
          {r.passed ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-pass" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-fail" />}
          <span>
            {r.label}
            {r.detail && <span className="ml-1 text-xs text-muted">({r.detail})</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Metric({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div title={hint}>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="font-display text-xl font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

const METRIC: Record<string, string> = { mrr: "MRR", hit_rate: "Hit rate", avg_latency_ms: "Avg latency", answer_accuracy: "Answer accuracy", grounded_rate: "Grounded answers", pass_rate: "Pass rate" };
export function metricLabel(k: string) {
  return METRIC[k] ?? (k.startsWith("recall@") ? `Recall@${k.slice(7)}` : k.replace(/_/g, " "));
}

export function pct(v: number | null | undefined) {
  return v === null || v === undefined ? "–" : `${Math.round(v * 100)}%`;
}

export function SimulatorNote() {
  return (
    <p className="text-xs text-faint">
      On the Free plan, model calls go to a deterministic simulator. It doesn't understand language, but it reproduces common model
      behaviour - following injected instructions unless your prompt treats input as data, wrapping JSON in prose unless you ask for
      only JSON, copying few-shot formats - so you can practise the techniques. Paid plans use the server's configured model.
    </p>
  );
}
