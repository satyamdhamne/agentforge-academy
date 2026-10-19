import { useQuery } from "@tanstack/react-query";
import { Award, Lock } from "lucide-react";
import { api } from "@/lib/api";
import type { Achievement, TrackSummary } from "@/lib/types";
import { CATEGORY_LABEL, cn, formatDate } from "@/lib/utils";
import { PageHeader, ErrorState } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { TrackRow } from "./Paths";

interface ProgressData { tracks: TrackSummary[]; challenges_by_category: Record<string, number>; activity_days: string[]; streak_days: number }

function Heatmap({ days }: { days: string[] }) {
  const set = new Set(days);
  const today = new Date();
  const cells = Array.from({ length: 84 }, (_, i) => {
    const d = new Date(today);
    d.setUTCDate(d.getUTCDate() - (83 - i));
    const key = d.toISOString().slice(0, 10);
    return { key, on: set.has(key) };
  });
  return (
    <div className="grid w-fit grid-flow-col grid-rows-7 gap-1" role="img" aria-label={`Active on ${days.length} days in the last 12 weeks`}>
      {cells.map((c) => <span key={c.key} title={c.key} className={cn("size-3 rounded-[3px]", c.on ? "bg-pass" : "bg-panel-2")} />)}
    </div>
  );
}

export default function ProgressPage() {
  const p = useQuery({ queryKey: ["my-progress"], queryFn: () => api.get<ProgressData>("/me/progress") });
  const a = useQuery({ queryKey: ["achievements"], queryFn: () => api.get<{ items: Achievement[] }>("/achievements") });
  if (p.isLoading) return <PageSkeleton />;
  if (p.error) return <ErrorState error={p.error} onRetry={() => p.refetch()} />;
  const d = p.data!;
  return (
    <div className="space-y-12">
      <PageHeader title="Progress & achievements" description="Everything here comes from verifiable records: completed lessons with a passed quiz, challenges that passed tests or review, and recorded agent runs." />
      <section className="grid gap-8 lg:grid-cols-[auto_1fr]">
        <div>
          <h2 className="mb-3 font-display text-lg font-semibold">Activity, last 12 weeks</h2>
          <Heatmap days={d.activity_days} />
          <p className="mt-2 text-sm text-muted">Current streak: {d.streak_days} {d.streak_days === 1 ? "day" : "days"}</p>
        </div>
        <div>
          <h2 className="mb-3 font-display text-lg font-semibold">Challenges solved by area</h2>
          {Object.keys(d.challenges_by_category).length ? (
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              {Object.entries(d.challenges_by_category).map(([k, v]) => <div key={k}><dt className="text-xs text-muted">{CATEGORY_LABEL[k] ?? k}</dt><dd className="font-display text-2xl font-semibold">{v}</dd></div>)}
            </dl>
          ) : <p className="text-sm text-muted">No challenges solved yet.</p>}
        </div>
      </section>
      <section>
        <h2 className="mb-3 font-display text-lg font-semibold">Paths in progress</h2>
        {d.tracks.length ? <div className="divide-y divide-line border-y border-line">{d.tracks.map((t) => <TrackRow key={t.slug} t={t} />)}</div> : <p className="text-sm text-muted">Enroll in a path or complete a lesson to see it here.</p>}
      </section>
      <section>
        <h2 className="mb-3 font-display text-lg font-semibold">Achievements</h2>
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {a.data?.items.map((x) => (
            <li key={x.slug} className={cn("flex gap-3 rounded-lg border p-4", x.earned ? "border-pass/40" : "border-line opacity-70")}>
              {x.earned ? <Award className="size-5 shrink-0 text-pass" /> : <Lock className="size-5 shrink-0 text-faint" />}
              <div>
                <p className="font-medium">{x.name}</p>
                <p className="text-sm text-muted">{x.description}</p>
                {x.earned && <p className="mt-1 text-xs text-pass">Earned {formatDate(x.awarded_at)}</p>}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
