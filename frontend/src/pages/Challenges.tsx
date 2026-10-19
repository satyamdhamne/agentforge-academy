import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Clock, Lock } from "lucide-react";
import { api } from "@/lib/api";
import type { ExerciseCard, Paged } from "@/lib/types";
import { CATEGORY_LABEL, cn } from "@/lib/utils";
import { PageHeader, ErrorState, EmptyState } from "@/components/States";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { LevelPips } from "@/components/Meta";

const KIND_LABEL: Record<string, string> = { code: "Auto-graded code", multiple_choice: "Multiple choice", manual_review: "Reviewed by a person" };

export function ChallengeRow({ c }: { c: ExerciseCard }) {
  return (
    <Link to={`/challenges/${c.slug}`} className="grid items-center gap-x-4 gap-y-1 px-4 py-3.5 hover:bg-panel-2/50 sm:grid-cols-[1.5rem_1fr_8rem_7rem_4.5rem]">
      <span className="hidden sm:block">{c.solved ? <CheckCircle2 className="size-4 text-pass" aria-label="Solved" /> : c.locked ? <Lock className="size-4 text-tool" aria-label="Locked" /> : null}</span>
      <span className="min-w-0">
        <span className="font-medium">{c.title}</span>
        <span className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted">
          <span>{CATEGORY_LABEL[c.category] ?? c.category}</span>
          <span>{KIND_LABEL[c.kind]}{c.language ? `, ${c.language}` : ""}</span>
          {c.time_limit_minutes && <span className="inline-flex items-center gap-1"><Clock className="size-3" />{c.time_limit_minutes} min</span>}
          {c.is_weekly_project && <span className="text-tool">Weekly project</span>}
        </span>
      </span>
      <LevelPips level={c.difficulty} />
      <span className="text-xs text-muted">{c.tier !== "free" ? "Pro" : ""}</span>
      <span className="text-right text-sm tabular-nums text-muted">{c.points} pts</span>
    </Link>
  );
}

export default function Challenges() {
  const [params, setParams] = useSearchParams();
  const filters = { category: params.get("category") ?? "", difficulty: params.get("difficulty") ?? "", q: params.get("q") ?? "" };
  const set = (k: string, v: string) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p, { replace: true }); };
  const daily = useQuery({ queryKey: ["daily"], queryFn: () => api.get<ExerciseCard & { date: string; solved: boolean }>("/challenges/daily") });
  const list = useQuery({
    queryKey: ["challenges", filters],
    queryFn: () => api.get<Paged<ExerciseCard> & { categories: string[] }>("/challenges", { params: { ...filters, page_size: 100 } }),
    placeholderData: (prev) => prev,
  });
  return (
    <div>
      <PageHeader title="Challenges" description="Graded practice across coding, debugging, RAG tuning, agent reliability, security, cloud and architecture. Points are awarded once per challenge; hints reduce them a little." />
      {daily.data && (
        <Link to={`/challenges/${daily.data.slug}`} className="mb-10 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-signal/40 bg-signal/5 px-5 py-4 hover:border-signal">
          <div>
            <p className="text-xs text-signal">Daily challenge for {daily.data.date}</p>
            <p className="mt-0.5 font-display text-lg font-semibold">{daily.data.title}</p>
          </div>
          <div className="ml-auto flex items-center gap-5 text-sm text-muted">
            <LevelPips level={daily.data.difficulty} />
            <span>{daily.data.points} points</span>
            {daily.data.solved && <span className="text-pass">Solved</span>}
          </div>
        </Link>
      )}

      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter by category">
        {["", ...(list.data?.categories ?? [])].map((c) => (
          <button key={c || "all"} onClick={() => set("category", c)} aria-pressed={filters.category === c}
            className={cn("rounded-full border px-3 py-1 text-sm", filters.category === c ? "border-signal bg-signal/10 text-fg" : "border-line text-muted hover:text-fg")}>
            {c ? CATEGORY_LABEL[c] ?? c : "All"}
          </button>
        ))}
      </div>
      <div className="mb-4 flex flex-wrap gap-3">
        <Input aria-label="Search challenges" placeholder="Search challenges" className="max-w-xs" defaultValue={filters.q} onChange={(e) => set("q", e.target.value)} />
        <Select aria-label="Difficulty" className="w-44" value={filters.difficulty} onChange={(e) => set("difficulty", e.target.value)}>
          <option value="">Any difficulty</option>
          <option value="beginner">Beginner</option>
          <option value="intermediate">Intermediate</option>
          <option value="advanced">Advanced</option>
          <option value="expert">Expert</option>
        </Select>
      </div>

      {list.isLoading && <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && (list.data.items.length ? (
        <div className="divide-y divide-line rounded-lg border border-line">{list.data.items.map((c) => <ChallengeRow key={c.slug} c={c} />)}</div>
      ) : (
        <EmptyState title="No challenges match these filters">Clear a filter to see more.</EmptyState>
      ))}
    </div>
  );
}
