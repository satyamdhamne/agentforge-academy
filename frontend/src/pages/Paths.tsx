import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { TrackSummary } from "@/lib/types";
import { PageHeader, ErrorState } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { LevelPips } from "@/components/Meta";

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-panel-2" role="progressbar" aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className="h-full rounded-full bg-pass" style={{ width: `${Math.round(value * 100)}%` }} />
    </div>
  );
}

export function TrackRow({ t }: { t: TrackSummary }) {
  return (
    <Link to={`/paths/${t.slug}`} className="group grid gap-3 py-4 sm:grid-cols-[1fr_12rem_9rem] sm:items-center">
      <div className="min-w-0">
        <p className="font-medium group-hover:text-signal">{t.title}</p>
        <p className="mt-0.5 line-clamp-2 text-sm text-muted">{t.summary}</p>
      </div>
      <div className="text-xs text-muted">
        {t.lessons_available > 0 ? (
          <>
            <ProgressBar value={t.progress} label={`${t.title} progress`} />
            <p className="mt-1.5 tabular-nums">
              {t.lessons_completed} of {t.lessons_available} ready {t.lessons_available === 1 ? "lesson" : "lessons"} done
              {t.lessons_total > t.lessons_available && <span className="text-faint">, {t.lessons_total - t.lessons_available} more coming</span>}
            </p>
          </>
        ) : (
          <p className="text-faint">{t.lessons_total} lessons outlined, first ones coming soon</p>
        )}
      </div>
      <div className="flex items-center gap-3 sm:justify-end">
        <LevelPips level={t.level} />
      </div>
    </Link>
  );
}

export default function Paths() {
  const q = useQuery({ queryKey: ["tracks"], queryFn: () => api.get<{ items: TrackSummary[] }>("/tracks") });
  return (
    <div>
      <PageHeader title="Learning paths" description="Sixteen tracks organised as Track › Course › Module › Lesson. Lessons marked as coming soon are outlined and ship weekly." />
      {q.isLoading && <PageSkeleton />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && <div className="divide-y divide-line border-y border-line">{q.data.items.map((t) => <TrackRow key={t.slug} t={t} />)}</div>}
    </div>
  );
}
