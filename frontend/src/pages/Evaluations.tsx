import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { GitCompare } from "lucide-react";
import { api } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, PageHeader } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { CheckList, Metric, metricLabel, ModeBadge, pct } from "@/components/LabBits";

/* eslint-disable @typescript-eslint/no-explicit-any */
interface Ev { id: string; name: string; target_type: "prompt" | "rag" | "agent"; summary: Record<string, any>; created_at: string;
  cases?: { key: string; input: any; expected: any; result: any; passed: boolean }[] }

const KIND: Record<string, string> = { prompt: "Prompt comparison", rag: "RAG retrieval", agent: "Agent evaluation" };
const TONE: Record<string, "signal" | "llm" | "tool"> = { prompt: "llm", rag: "signal", agent: "tool" };

function headline(e: Ev): { label: string; value: number | null | undefined } {
  const s = e.summary ?? {};
  if (s.kind === "rag_eval") return { label: "hit rate", value: s.metrics?.hit_rate };
  if (s.kind === "prompt_compare") return { label: `best: ${s.best}`, value: s.variants?.find((v: any) => v.label === s.best)?.pass_rate };
  return { label: "pass rate", value: s.pass_rate };
}

export function EvaluationsList() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const type = params.get("type") ?? "";
  const [sel, setSel] = useState<string[]>([]);
  const q = useQuery({ queryKey: ["evaluations", type], queryFn: () => api.get<{ items: Ev[] }>("/evaluations", { params: { target_type: type || undefined } }) });
  const items = q.data?.items ?? [];
  const selType = items.find((e) => e.id === sel[0])?.target_type;
  return (
    <div>
      <PageHeader title="Evaluations" description="Every prompt comparison, RAG evaluation and agent test run you've made. Pick two of the same kind to see what changed."
        actions={<Button variant="secondary" disabled={sel.length !== 2} onClick={() => nav(`/evaluations/compare?a=${sel[0]}&b=${sel[1]}`)}><GitCompare />Compare selected</Button>} />
      <div className="mb-6 flex gap-1" role="tablist" aria-label="Filter by kind">
        {[["", "All"], ["prompt", "Prompts"], ["rag", "RAG"], ["agent", "Agents"]].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={type === k} onClick={() => { setParams(k ? { type: k } : {}); setSel([]); }}
            className={cn("rounded-md px-3 py-1.5 text-sm", type === k ? "bg-panel-2 text-fg" : "text-muted hover:text-fg")}>{l}</button>
        ))}
      </div>
      {q.isLoading ? <PageSkeleton /> : q.error ? <ErrorState error={q.error} /> : items.length === 0 ? (
        <EmptyState title="No evaluations yet">
          Run a comparison in the <Link className="text-signal hover:underline" to="/labs/prompts">Prompt Lab</Link>, an evaluation in the{" "}
          <Link className="text-signal hover:underline" to="/labs/rag">RAG Lab</Link>, or the test suite of any agent in the <Link className="text-signal hover:underline" to="/agents">Agent Library</Link>.
        </EmptyState>
      ) : (
        <ul className="divide-y divide-line rounded-lg border border-line">
          {items.map((e) => {
            const h = headline(e);
            const disabled = sel.length > 0 && !sel.includes(e.id) && (sel.length >= 2 || e.target_type !== selType);
            return (
              <li key={e.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <input type="checkbox" aria-label={`Select ${e.name}`} className="accent-[var(--signal)]" disabled={disabled} checked={sel.includes(e.id)}
                  onChange={(ev) => setSel(ev.target.checked ? [...sel, e.id] : sel.filter((x) => x !== e.id))} />
                <Badge tone={TONE[e.target_type]}>{KIND[e.target_type]}</Badge>
                <Link to={`/evaluations/${e.id}`} className="min-w-0 flex-1 truncate font-medium hover:text-signal">{e.name}</Link>
                <span className="text-sm tabular-nums">{pct(h.value)} <span className="text-muted">{h.label}</span></span>
                <span className="w-28 text-right text-xs text-muted">{formatDate(e.created_at)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function RagSummary({ s }: { s: any }) {
  return (
    <>
      <dl className="grid grid-cols-2 gap-4 rounded-lg border border-line p-4 sm:grid-cols-4">
        {Object.entries(s.metrics ?? {}).map(([k, v]) => <Metric key={k} label={metricLabel(k)} value={k.includes("latency") ? `${v} ms` : k === "mrr" ? (v as number).toFixed(2) : pct(v as number)} />)}
      </dl>
      <p className="text-sm text-muted">Dataset {s.dataset}: {s.strategy} retrieval, {s.config?.chunker} chunks of {s.config?.size} words ({s.config?.overlap} overlap), {s.config?.embedder}, top {s.top_k}{s.rerank ? ", reranked" : ""}.</p>
    </>
  );
}

export function EvaluationDetail() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["evaluation", id], queryFn: () => api.get<Ev>(`/evaluations/${id}`) });
  if (q.isLoading) return <PageSkeleton />;
  if (q.error || !q.data) return <ErrorState error={q.error} />;
  const e = q.data;
  const s = e.summary ?? {};
  return (
    <div className="space-y-8">
      <div>
        <Link to="/evaluations" className="text-sm text-muted hover:text-fg">Evaluations</Link>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <h1 className="text-3xl font-semibold">{e.name}</h1>
          <Badge tone={TONE[e.target_type]}>{KIND[e.target_type]}</Badge><ModeBadge mode={s.mode} label={s.provider} />
        </div>
        <p className="mt-1 text-sm text-muted">{formatDate(e.created_at)}</p>
      </div>
      {s.kind === "rag_eval" && <RagSummary s={s} />}
      {s.kind === "prompt_compare" && (
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-sm">
            <thead className="bg-panel-2 text-left text-muted"><tr><th className="px-3 py-2 font-medium">Variant</th><th className="px-3 py-2 font-medium">Cases passed</th><th className="px-3 py-2 font-medium">Checks passed</th><th className="px-3 py-2 font-medium">Avg tokens in/out</th><th className="px-3 py-2 font-medium">Cost</th></tr></thead>
            <tbody>{(s.variants ?? []).map((v: any) => (
              <tr key={v.label} className="border-t border-line"><td className="px-3 py-2 font-medium">{v.label}{v.label === s.best && <Badge tone="pass" className="ml-2">best</Badge>}</td>
                <td className="px-3 py-2">{pct(v.pass_rate)}</td><td className="px-3 py-2">{pct(v.check_pass_rate)}</td><td className="px-3 py-2">{v.avg_input_tokens} / {v.avg_output_tokens}</td><td className="px-3 py-2">${Number(v.cost_usd).toFixed(5)}</td></tr>))}</tbody>
          </table>
        </div>
      )}
      {s.kind === "agent_eval" && (
        <dl className="grid grid-cols-3 gap-4 rounded-lg border border-line p-4"><Metric label="Pass rate" value={pct(s.pass_rate)} /><Metric label="Passed" value={`${s.passed} / ${s.cases}`} />
          <Metric label="Agent" value={<Link className="text-base text-signal hover:underline" to={`/agents/${s.agent}`}>{s.agent}</Link>} /></dl>
      )}
      <section>
        <h2 className="mb-3 font-display text-lg font-semibold">Cases</h2>
        <ul className="divide-y divide-line rounded-lg border border-line">
          {(e.cases ?? []).map((c) => (
            <li key={c.key} className="p-3">
              <details>
                <summary className="flex cursor-pointer flex-wrap items-center gap-2">
                  <Badge tone={c.passed ? "pass" : "fail"}>{c.passed ? "pass" : "fail"}</Badge><span className="text-sm">{c.result?.question ?? c.key}</span>
                </summary>
                <div className="mt-3 space-y-2 text-sm">
                  {c.result?.output !== undefined && <pre className="max-h-60 overflow-auto whitespace-pre-wrap rounded bg-sunken p-2 font-mono text-xs">{c.result.error ?? c.result.output}</pre>}
                  {c.result?.checks?.results && <CheckList results={c.result.checks.results} />}
                  {Array.isArray(c.result?.checks) && <CheckList results={c.result.checks.map((x: any) => ({ ...x, label: x.check, type: "" }))} />}
                  {c.result?.retrieved_sources && <p className="text-muted">Expected {c.result.relevant.join(", ") || "nothing"}; retrieved {c.result.retrieved_sources.join(", ") || "nothing"}.</p>}
                  {c.result?.answer && <p className="text-muted">Answer: {c.result.answer}</p>}
                  {c.result?.error && !c.result?.output && <p className="text-fail">{c.result.error}</p>}
                </div>
              </details>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export function EvaluationCompare() {
  const [params] = useSearchParams();
  const a = params.get("a"), b = params.get("b");
  const q = useQuery({ queryKey: ["eval-compare", a, b], queryFn: () => api.get<{ a: Ev; b: Ev; metrics: { metric: string; a: number | null; b: number | null; delta: number | null }[] }>(`/evaluations/${a}/compare/${b}`), enabled: !!a && !!b });
  if (q.isLoading) return <PageSkeleton />;
  if (q.error || !q.data) return <ErrorState error={q.error ?? new Error("Pick two evaluations to compare.")} />;
  const lowerBetter = (m: string) => m.includes("latency") || m.includes("tokens");
  return (
    <div className="space-y-6">
      <Link to="/evaluations" className="text-sm text-muted hover:text-fg">Evaluations</Link>
      <h1 className="text-3xl font-semibold">Comparison</h1>
      <div className="grid gap-3 md:grid-cols-2">
        {[q.data.a, q.data.b].map((e, i) => (
          <Link key={e.id} to={`/evaluations/${e.id}`} className="rounded-lg border border-line p-3 hover:border-line-strong">
            <span className="font-mono text-xs text-faint">{i === 0 ? "A (before)" : "B (after)"}</span><p className="font-medium">{e.name}</p><p className="text-xs text-muted">{formatDate(e.created_at)}</p>
          </Link>
        ))}
      </div>
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel-2 text-left text-muted"><tr><th className="px-3 py-2 font-medium">Metric</th><th className="px-3 py-2 font-medium">A</th><th className="px-3 py-2 font-medium">B</th><th className="px-3 py-2 font-medium">Change</th></tr></thead>
          <tbody>{q.data.metrics.map((m) => {
            const better = m.delta === null || m.delta === 0 ? null : (m.delta > 0) !== lowerBetter(m.metric);
            return (
              <tr key={m.metric} className="border-t border-line"><td className="px-3 py-2">{metricLabel(m.metric)}</td><td className="px-3 py-2 tabular-nums">{m.a ?? "–"}</td><td className="px-3 py-2 tabular-nums">{m.b ?? "–"}</td>
                <td className={cn("px-3 py-2 tabular-nums", better === true && "text-pass", better === false && "text-fail")}>{m.delta === null ? "–" : `${m.delta > 0 ? "+" : ""}${m.delta}`}</td></tr>
            );
          })}</tbody>
        </table>
      </div>
    </div>
  );
}
