import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { AgentCard } from "@/lib/types";
import { VERDICT_HELP, VERDICT_LABEL, cn } from "@/lib/utils";
import { PageHeader, ErrorState, EmptyState } from "@/components/States";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { LevelPips } from "@/components/Meta";

interface AgentList { items: AgentCard[]; total: number; facets: { categories: Record<string, number>; verdicts: Record<string, number> } }

export const VERDICT_TONE: Record<string, "pass" | "signal" | "tool" | "llm"> = { deterministic: "pass", workflow: "signal", rag: "tool", agent: "llm" };

export default function Agents() {
  const [params, setParams] = useSearchParams();
  const f = { category: params.get("category") ?? "", verdict: params.get("verdict") ?? "", implemented: params.get("implemented") ?? "", q: params.get("q") ?? "" };
  const set = (k: string, v: string) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p, { replace: true }); };
  const all = useQuery({ queryKey: ["agents", {}], queryFn: () => api.get<AgentList>("/agents") });
  const q = useQuery({ queryKey: ["agents", f], queryFn: () => api.get<AgentList>("/agents", { params: f }), placeholderData: (p) => p });
  const facets = all.data?.facets;

  return (
    <div>
      <PageHeader
        title="AI Agent Library"
        description="A hundred practical blueprints across twelve business areas. Ten have complete, tested reference implementations you can run, trace and evaluate. Each entry says honestly whether it should be an agent at all."
      />
      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4" role="group" aria-label="Filter by recommended approach">
        {(["deterministic", "workflow", "rag", "agent"] as const).map((v) => (
          <button key={v} onClick={() => set("verdict", f.verdict === v ? "" : v)} aria-pressed={f.verdict === v}
            className={cn("rounded-lg border p-3 text-left transition-colors", f.verdict === v ? "border-signal bg-signal/5" : "border-line hover:border-line-strong")}>
            <span className="flex items-center justify-between">
              <span className="font-medium">{VERDICT_LABEL[v]}</span>
              <span className="font-mono text-sm text-muted">{facets?.verdicts[v] ?? ""}</span>
            </span>
            <span className="mt-1 block text-xs text-muted">{VERDICT_HELP[v]}</span>
          </button>
        ))}
      </div>
      <div className="mb-5 flex flex-wrap gap-3">
        <Input aria-label="Search agents" placeholder="Search by name or problem" className="max-w-xs" defaultValue={f.q} onChange={(e) => set("q", e.target.value)} />
        <Select aria-label="Category" className="w-60" value={f.category} onChange={(e) => set("category", e.target.value)}>
          <option value="">All categories</option>
          {facets && Object.entries(facets.categories).map(([c, n]) => <option key={c} value={c}>{c} ({n})</option>)}
        </Select>
        <label className="flex items-center gap-2 text-sm text-muted">
          <input type="checkbox" className="accent-[var(--signal)]" checked={f.implemented === "true"} onChange={(e) => set("implemented", e.target.checked ? "true" : "")} />
          Runnable reference implementations only
        </label>
      </div>

      {q.isLoading && <div className="grid gap-3 sm:grid-cols-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-28" />)}</div>}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && (q.data.items.length === 0 ? (
        <EmptyState title="No agents match">Try another category or clear the search.</EmptyState>
      ) : (
        <>
          <p className="mb-3 text-sm text-muted">{q.data.total} {q.data.total === 1 ? "entry" : "entries"}</p>
          <ul className="grid gap-3 sm:grid-cols-2">
            {q.data.items.map((a) => (
              <li key={a.slug}>
                <Link to={`/agents/${a.slug}`} className={cn("flex h-full flex-col rounded-lg border p-4 transition-colors hover:border-line-strong", a.has_reference_impl ? "border-line bg-panel" : "border-line/70")}>
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 font-mono text-xs text-faint tabular-nums">{String(a.number).padStart(3, "0")}</span>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{a.name}</p>
                      <p className="text-xs text-muted">{a.category}</p>
                    </div>
                    {a.has_reference_impl ? <Badge tone="pass">Runnable</Badge> : <Badge>Blueprint</Badge>}
                  </div>
                  <p className="mt-2 line-clamp-2 flex-1 text-sm text-muted">{a.summary}</p>
                  <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted">
                    <Badge tone={VERDICT_TONE[a.verdict]}>{VERDICT_LABEL[a.verdict]}</Badge>
                    <LevelPips level={a.level} />
                    <span>~{a.build_hours} h to build</span>
                    {a.tier !== "free" && <Badge tone="outline">Pro</Badge>}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </>
      ))}
    </div>
  );
}
