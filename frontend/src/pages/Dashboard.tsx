import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Dashboard as D } from "@/lib/types";
import { CATEGORY_LABEL } from "@/lib/utils";
import { PageSkeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/States";
import { Button } from "@/components/ui/button";
import { LevelPips } from "@/components/Meta";
import { Markdown } from "@/components/Markdown";
import { TrackRow } from "./Paths";

export default function Dashboard() {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<D>("/me/dashboard") });
  const ann = useQuery({ queryKey: ["announcements"], queryFn: () => api.get<{ items: { id: string; title: string; body_md: string }[] }>("/announcements") });
  if (q.isLoading) return <PageSkeleton />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data!;
  const s = d.stats;
  const firstName = user?.profile.display_name.split(" ")[0];
  return (
    <div className="space-y-12">
      <section className="grid gap-8 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <p className="text-sm text-muted">Welcome back{firstName ? `, ${firstName}` : ""}</p>
          {d.continue_lesson ? (
            <>
              <h1 className="mt-1 text-3xl font-semibold leading-tight">{d.continue_lesson.title}</h1>
              <p className="mt-1 text-muted">Next up in {d.continue_lesson.track}</p>
              <Button asChild className="mt-5"><Link to={`/lessons/${d.continue_lesson.slug}`}>Continue lesson</Link></Button>
            </>
          ) : (
            <>
              <h1 className="mt-1 text-3xl font-semibold">Pick your first path</h1>
              <p className="mt-1 text-muted">Enroll in a track and we’ll keep your place.</p>
              <Button asChild className="mt-5"><Link to="/paths">Browse learning paths</Link></Button>
            </>
          )}
          <dl className="mt-10 grid grid-cols-2 gap-x-6 gap-y-5 border-t border-line pt-6 sm:grid-cols-5">
            {[
              ["Lessons completed", s.lessons_completed],
              ["Challenges solved", s.challenges_solved],
              ["Points", s.points],
              ["Day streak", s.streak_days],
              ["Agent runs", s.agent_runs],
            ].map(([label, value]) => (
              <div key={label as string}>
                <dt className="text-xs text-muted">{label}</dt>
                <dd className="font-display text-2xl font-semibold tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="rounded-lg border border-line bg-panel p-5">
          <div className="flex items-baseline justify-between">
            <h2 className="font-display text-lg font-semibold">Daily challenge</h2>
            <span className="text-xs text-muted">Resets at 00:00 UTC</span>
          </div>
          {d.daily_challenge ? (
            <Link to={`/challenges/${d.daily_challenge.slug}`} className="group mt-3 block">
              <p className="text-xs text-muted">{CATEGORY_LABEL[d.daily_challenge.category] ?? d.daily_challenge.category}, {d.daily_challenge.points} points</p>
              <p className="mt-1 font-medium group-hover:text-signal">{d.daily_challenge.title}</p>
              <div className="mt-2"><LevelPips level={d.daily_challenge.difficulty} /></div>
            </Link>
          ) : <p className="mt-3 text-sm text-muted">No challenge today.</p>}
          <div className="mt-6 h-28" aria-label="Activity over the last 7 days">
            <p className="mb-1 text-xs text-muted">Activity, last 7 days</p>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={d.activity.map((a) => ({ ...a, day: new Date(a.date + "T00:00:00").toLocaleDateString(undefined, { weekday: "short" }) }))}>
                <XAxis dataKey="day" tickLine={false} axisLine={false} tick={{ fill: "var(--fg-faint)", fontSize: 11 }} />
                <Tooltip cursor={{ fill: "var(--panel-2)" }} contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 6, fontSize: 12 }} />
                <Bar dataKey="count" name="Completions & attempts" fill="var(--signal)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      {ann.data?.items[0] && (
        <aside className="rounded-lg border border-line px-4 py-3 text-sm" aria-label="Announcement">
          <p className="font-medium">{ann.data.items[0].title}</p>
          <Markdown className="mt-1 max-w-none text-muted [&_p]:m-0">{ann.data.items[0].body_md}</Markdown>
        </aside>
      )}

      <section>
        <h2 className="mb-3 font-display text-xl font-semibold">Your paths</h2>
        {d.enrolled_tracks.length ? (
          <div className="divide-y divide-line border-y border-line">{d.enrolled_tracks.map((t) => <TrackRow key={t.slug} t={t} />)}</div>
        ) : (
          <p className="text-sm text-muted">You haven’t enrolled in a path yet. Recommended starting points are below.</p>
        )}
      </section>

      {d.recommended_tracks.length > 0 && (
        <section>
          <h2 className="mb-3 font-display text-xl font-semibold">Recommended next</h2>
          <div className="divide-y divide-line border-y border-line">{d.recommended_tracks.map((t) => <TrackRow key={t.slug} t={t} />)}</div>
        </section>
      )}

      {d.recent_achievements.length > 0 && (
        <section>
          <h2 className="mb-3 font-display text-xl font-semibold">Recent achievements</h2>
          <ul className="flex flex-wrap gap-2">
            {d.recent_achievements.map((a) => <li key={a.slug} className="rounded-full border border-line px-3 py-1 text-sm">{a.name}</li>)}
          </ul>
        </section>
      )}
    </div>
  );
}
