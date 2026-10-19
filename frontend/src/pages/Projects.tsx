import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Lock } from "lucide-react";
import { api } from "@/lib/api";
import { PageHeader, ErrorState } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { LevelPips } from "@/components/Meta";
import { Badge } from "@/components/ui/badge";

interface Project { slug: string; title: string; summary: string; difficulty: string; track: string; skills: string[]; requirements: string[]; estimated_hours: number; tier: string; locked: boolean }

export default function Projects() {
  const q = useQuery({ queryKey: ["projects"], queryFn: () => api.get<{ items: Project[] }>("/projects") });
  return (
    <div>
      <PageHeader title="Real-world projects" description="Portfolio projects with explicit acceptance criteria. Build them in your own repository; publishing verified projects to a portfolio arrives with Phase 6." />
      {q.isLoading && <PageSkeleton />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      <div className="space-y-6">
        {q.data?.items.map((p) => (
          <article key={p.slug} className="grid gap-6 rounded-lg border border-line p-5 md:grid-cols-[1fr_1.1fr]">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-display text-xl font-semibold">{p.title}</h2>
                {p.locked && <Badge tone="tool"><Lock className="size-3" />Pro</Badge>}
              </div>
              <p className="mt-2 text-muted">{p.summary}</p>
              <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-muted">
                <LevelPips level={p.difficulty} />
                <span>About {p.estimated_hours} hours</span>
              </div>
              <ul className="mt-3 flex flex-wrap gap-1.5">{p.skills.map((s) => <li key={s}><Badge tone="outline">{s}</Badge></li>)}</ul>
            </div>
            <div>
              <h3 className="text-sm font-medium">Acceptance criteria</h3>
              <ul className="mt-2 space-y-1.5 text-sm">{p.requirements.map((r) => <li key={r} className="flex gap-2"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-faint" /><span>{r}</span></li>)}</ul>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
