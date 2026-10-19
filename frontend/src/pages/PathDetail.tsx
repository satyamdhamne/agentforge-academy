import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, Lock } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { TrackDetail } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { LevelPips } from "@/components/Meta";
import { ProgressBar } from "./Paths";

export default function PathDetail() {
  const { slug = "" } = useParams();
  const { user } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["track", slug], queryFn: () => api.get<TrackDetail>(`/tracks/${slug}`) });
  const enroll = useMutation({
    mutationFn: () => api.post(`/tracks/${slug}/enroll`),
    onSuccess: () => { toast.success("Enrolled. This path now appears on your dashboard."); qc.invalidateQueries({ queryKey: ["track", slug] }); qc.invalidateQueries({ queryKey: ["dashboard"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (q.isLoading) return <PageSkeleton />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const t = q.data!;
  const firstAvailable = t.courses_detail.flatMap((c) => c.modules.flatMap((m) => m.lessons)).find((l) => l.available && !l.completed && !l.locked);
  return (
    <div className="grid gap-10 lg:grid-cols-[1fr_17rem]">
      <div className="min-w-0">
        <Link to="/paths" className="text-sm text-muted hover:text-fg">Learning paths</Link>
        <h1 className="mt-2 text-4xl font-semibold leading-tight">{t.title}</h1>
        <p className="mt-3 max-w-2xl text-lg text-muted">{t.description}</p>

        <div className="mt-10 space-y-10">
          {t.courses_detail.map((c, ci) => (
            <section key={c.slug} aria-labelledby={`course-${c.slug}`}>
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="font-mono text-sm text-faint">Course {ci + 1}</span>
                <h2 id={`course-${c.slug}`} className="font-display text-xl font-semibold">{c.title}</h2>
                <span className="text-sm text-muted">about {c.estimated_hours} h</span>
              </div>
              {c.modules.map((m) => (
                <div key={m.slug} className="mt-4">
                  <h3 className="text-sm font-medium text-muted">{m.title}</h3>
                  <ol className="mt-2 divide-y divide-line rounded-lg border border-line">
                    {m.lessons.map((l) => {
                      const icon = l.completed ? <CheckCircle2 className="size-4 text-pass" /> : l.locked ? <Lock className="size-4 text-tool" /> : <Circle className="size-4 text-faint" />;
                      const body = (
                        <div className="flex items-center gap-3 px-4 py-3">
                          {icon}
                          <div className="min-w-0 flex-1">
                            <p className={l.available ? "font-medium" : "text-muted"}>{l.title}</p>
                            {l.summary && <p className="mt-0.5 line-clamp-1 text-sm text-muted">{l.summary}</p>}
                          </div>
                          {!l.available ? <Badge>Coming soon</Badge> : l.locked ? <Badge tone="tool">Pro</Badge> : <span className="text-xs text-muted tabular-nums">{l.minutes} min</span>}
                        </div>
                      );
                      return (
                        <li key={l.slug}>
                          {l.available ? <Link to={`/lessons/${l.slug}`} className="block hover:bg-panel-2/60">{body}</Link> : body}
                        </li>
                      );
                    })}
                  </ol>
                </div>
              ))}
            </section>
          ))}
        </div>
      </div>

      <aside className="lg:sticky lg:top-20 lg:self-start">
        <div className="space-y-5 rounded-lg border border-line p-5">
          <div>
            <ProgressBar value={t.progress} label="Track progress" />
            <p className="mt-2 text-sm text-muted tabular-nums">{t.lessons_completed} of {t.lessons_available} ready lessons complete</p>
          </div>
          <LevelPips level={t.level} />
          {firstAvailable && <Button asChild className="w-full"><Link to={`/lessons/${firstAvailable.slug}`}>{t.lessons_completed ? "Continue" : "Start the first lesson"}</Link></Button>}
          {user && !t.enrolled && <Button variant="secondary" className="w-full" onClick={() => enroll.mutate()} disabled={enroll.isPending}>Enroll in this path</Button>}
          {t.enrolled && <p className="text-sm text-pass">You’re enrolled in this path.</p>}
          {t.outcomes.length > 0 && (
            <div>
              <p className="text-sm font-medium">You’ll be able to</p>
              <ul className="mt-2 space-y-1.5 text-sm text-muted">{t.outcomes.map((o) => <li key={o} className="flex gap-2"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-signal" />{o}</li>)}</ul>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
