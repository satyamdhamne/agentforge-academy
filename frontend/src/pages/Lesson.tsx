import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, ChevronRight, Lock, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Achievement, Lesson, LessonSections } from "@/lib/types";
import { CATEGORY_LABEL, cn, formatDate } from "@/lib/utils";
import { Markdown } from "@/components/Markdown";
import { CodeRunner } from "@/components/CodeRunner";
import { Mermaid } from "@/components/Mermaid";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorState, EmptyState } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { LevelPips } from "@/components/Meta";

/** The fifteen parts every lesson carries, in reading order. */
const OUTLINE: { id: string; label: string; has: (s: LessonSections) => boolean }[] = [
  { id: "explanation", label: "The idea", has: (s) => !!s.explanation },
  { id: "why", label: "Why it matters", has: (s) => !!s.why_it_matters },
  { id: "prerequisites", label: "Prerequisites", has: (s) => s.prerequisites?.length > 0 },
  { id: "mental-model", label: "Mental model", has: (s) => !!s.mental_model },
  { id: "architecture", label: "Architecture", has: (s) => !!s.architecture?.mermaid },
  { id: "code", label: "Code you can run", has: (s) => s.code_examples?.length > 0 },
  { id: "real-world", label: "In the real world", has: (s) => !!s.real_world },
  { id: "mistakes", label: "Common mistakes", has: (s) => s.common_mistakes?.length > 0 },
  { id: "debugging", label: "Debugging", has: (s) => !!s.debugging },
  { id: "perf-security", label: "Performance & security", has: (s) => !!s.performance_security },
  { id: "interview", label: "Interview questions", has: (s) => s.interview_questions?.length > 0 },
  { id: "challenges", label: "Challenges", has: (s) => !!s.mini_challenge },
  { id: "reading", label: "Further reading", has: (s) => s.further_reading?.length > 0 },
  { id: "quiz", label: "Check your understanding", has: () => true },
];

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="scroll-mt-20">
      <h2 id={`${id}-h`} className="mb-3 font-display text-[22px] font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function useActiveSection(ids: string[]) {
  const [active, setActive] = useState(ids[0]);
  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        const vis = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (vis[0]) setActive(vis[0].target.id);
      },
      { rootMargin: "-80px 0px -65% 0px" },
    );
    ids.forEach((id) => { const el = document.getElementById(id); if (el) obs.observe(el); });
    return () => obs.disconnect();
  }, [ids.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps
  return active;
}

function Quiz({ lesson }: { lesson: Lesson }) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const submit = useMutation({
    mutationFn: () => api.post<{ score: number; passed: boolean; threshold: number; results: { id: string; correct: boolean; correct_index: number; explanation: string }[] }>(`/lessons/${lesson.slug}/quiz`, { answers }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lesson", lesson.slug] }),
  });
  const results = new Map(submit.data?.results.map((r) => [r.id, r]));
  if (!lesson.quiz.length) return <p className="text-sm text-muted">This lesson has no quiz.</p>;
  return (
    <div className="space-y-6">
      {lesson.quiz.map((q, qi) => {
        const r = results.get(q.id);
        return (
          <fieldset key={q.id} className="space-y-2">
            <legend className="mb-2 font-medium"><span className="mr-2 font-mono text-sm text-faint">{qi + 1}.</span>{q.prompt}</legend>
            {q.options.map((o, i) => {
              const chosen = answers[q.id] === i;
              const state = r ? (i === r.correct_index ? "right" : chosen ? "wrong" : "") : "";
              return (
                <label key={i} className={cn("flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2 text-sm",
                  state === "right" ? "border-pass/60 bg-pass/5" : state === "wrong" ? "border-fail/60 bg-fail/5" : chosen ? "border-signal" : "border-line hover:border-line-strong")}>
                  <input type="radio" name={q.id} className="mt-1 accent-[var(--signal)]" checked={chosen} onChange={() => { setAnswers({ ...answers, [q.id]: i }); submit.reset(); }} />
                  <span>{o}</span>
                </label>
              );
            })}
            {r && <p className={cn("text-sm", r.correct ? "text-pass" : "text-muted")}>{r.correct ? "Correct. " : ""}{r.explanation}</p>}
          </fieldset>
        );
      })}
      {user ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => submit.mutate()} disabled={Object.keys(answers).length < lesson.quiz.length || submit.isPending}>Check answers</Button>
          {submit.data && (
            <span className={cn("text-sm font-medium", submit.data.passed ? "text-pass" : "text-tool")}>
              {Math.round(submit.data.score * 100)}% - {submit.data.passed ? "passed" : `you need ${Math.round(submit.data.threshold * 100)}% to complete the lesson`}
            </span>
          )}
          {submit.error && <span className="text-sm text-fail">{errorMessage(submit.error)}</span>}
        </div>
      ) : (
        <p className="text-sm text-muted"><Link to="/login" className="text-signal hover:underline">Sign in</Link> to check your answers and save progress.</p>
      )}
    </div>
  );
}

function CompleteButton({ lesson }: { lesson: Lesson }) {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => api.post<{ status: string; new_achievements: Achievement[] }>(`/lessons/${lesson.slug}/progress`, { status: "completed" }),
    onSuccess: (r) => {
      toast.success("Lesson completed");
      r.new_achievements.forEach((a) => toast(`Achievement unlocked: ${a.name}`));
      qc.invalidateQueries({ queryKey: ["lesson", lesson.slug] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e) => toast.error(e instanceof ApiError && e.code === "quiz_required" ? e.message : errorMessage(e)),
  });
  if (lesson.progress?.status === "completed")
    return <p className="flex items-center gap-2 text-sm text-pass"><CheckCircle2 className="size-4" /> Completed {formatDate(lesson.progress.completed_at)}</p>;
  return <Button onClick={() => m.mutate()} disabled={m.isPending}>Mark lesson complete</Button>;
}

export default function LessonPage() {
  const { slug = "" } = useParams();
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["lesson", slug], queryFn: () => api.get<Lesson>(`/lessons/${slug}`) });
  const s = q.data?.content?.sections;
  const outline = s ? OUTLINE.filter((o) => o.has(s)) : [];
  const active = useActiveSection(outline.map((o) => o.id));

  if (q.isLoading) return <PageSkeleton />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const l = q.data!;

  const header = (
    <header className="mb-10">
      <nav aria-label="Breadcrumb" className="text-sm text-muted">
        <Link to={`/paths/${l.breadcrumb.track.slug}`} className="hover:text-fg">{l.breadcrumb.track.title}</Link>
        <span className="mx-1.5 text-faint">/</span>{l.breadcrumb.course}
        <span className="mx-1.5 text-faint">/</span>{l.breadcrumb.module}
      </nav>
      <h1 className="mt-3 max-w-[24ch] text-4xl font-semibold leading-[1.1]">{l.title}</h1>
      <p className="mt-3 max-w-[62ch] text-lg text-muted">{l.summary}</p>
      <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-muted">
        <LevelPips level={l.level} />
        <span>{l.minutes} minutes</span>
        <span>Version {l.version}, updated {formatDate(l.updated_at)}</span>
      </div>
    </header>
  );

  if (l.locked || !s)
    return (
      <div className="max-w-3xl">
        {header}
        <EmptyState title="This lesson is part of the Pro plan" action={<Button asChild><Link to="/pricing"><Lock />See plans</Link></Button>}>
          Upgrade to unlock every lesson in this path, advanced projects and real-model agent runs.
        </EmptyState>
      </div>
    );

  return (
    <div className="grid gap-10 xl:grid-cols-[13rem_minmax(0,1fr)]">
      <aside className="hidden xl:block">
        <nav aria-label="Lesson sections" className="sticky top-20">
          <p className="mb-2 text-xs font-medium text-faint">On this page</p>
          <ol className="space-y-0.5 border-l border-line">
            {outline.map((o) => (
              <li key={o.id}>
                <a href={`#${o.id}`} className={cn("-ml-px block border-l-2 py-1 pl-3 text-[13px]", active === o.id ? "border-signal text-fg" : "border-transparent text-muted hover:text-fg")}>{o.label}</a>
              </li>
            ))}
          </ol>
        </nav>
      </aside>

      <article className="min-w-0 max-w-3xl">
        {header}
        <div className="space-y-12">
          <Section id="explanation" title="The idea"><Markdown>{s.explanation}</Markdown></Section>
          <Section id="why" title="Why it matters"><Markdown>{s.why_it_matters}</Markdown></Section>
          {s.prerequisites?.length > 0 && (
            <Section id="prerequisites" title="Prerequisites">
              <div className="prose-af"><ul>{s.prerequisites.map((p) => <li key={p}>{p}</li>)}</ul></div>
              {l.prerequisites.length > 0 && (
                <p className="mt-2 text-sm text-muted">Related lessons: {l.prerequisites.map((p, i) => <span key={p}>{i > 0 && ", "}<Link to={`/lessons/${p}`} className="text-signal hover:underline">{p}</Link></span>)}</p>
              )}
            </Section>
          )}
          <Section id="mental-model" title="Mental model">
            <div className="border-l-2 border-llm/60 pl-4"><Markdown>{s.mental_model}</Markdown></div>
          </Section>
          {s.architecture?.mermaid && (
            <Section id="architecture" title="Architecture">
              <Mermaid chart={s.architecture.mermaid} />
              {s.architecture.caption && <p className="mt-2 text-sm text-muted">{s.architecture.caption}</p>}
            </Section>
          )}
          <Section id="code" title="Code you can run">
            <div className="space-y-10">
              {s.code_examples.map((ex) => (
                <div key={ex.title}>
                  <div className="mb-2 flex items-baseline gap-2">
                    <h3 className="font-medium">{ex.title}</h3>
                    <Badge tone="outline">{ex.language}</Badge>
                  </div>
                  <CodeRunner example={ex} />
                  {ex.annotations && ex.annotations.length > 0 && (
                    <ul className="mt-3 space-y-1.5 text-sm text-muted">
                      {ex.annotations.map((a) => <li key={a} className="flex gap-2"><span className="text-signal">›</span><Markdown className="[&_p]:m-0">{a}</Markdown></li>)}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </Section>
          <Section id="real-world" title="In the real world"><Markdown>{s.real_world}</Markdown></Section>
          <Section id="mistakes" title="Common mistakes">
            <dl className="divide-y divide-line rounded-lg border border-line">
              {s.common_mistakes.map((m) => (
                <div key={m.mistake} className="grid gap-1 p-4 sm:grid-cols-2 sm:gap-6">
                  <dt className="flex gap-2 text-sm"><XCircle className="mt-0.5 size-4 shrink-0 text-fail" /><Markdown className="[&_p]:m-0">{m.mistake}</Markdown></dt>
                  <dd className="flex gap-2 text-sm text-muted"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-pass" /><Markdown className="[&_p]:m-0">{m.fix}</Markdown></dd>
                </div>
              ))}
            </dl>
          </Section>
          <Section id="debugging" title="Debugging"><Markdown>{s.debugging}</Markdown></Section>
          <Section id="perf-security" title="Performance & security"><Markdown>{s.performance_security}</Markdown></Section>
          <Section id="interview" title="Interview questions">
            <div className="divide-y divide-line border-y border-line">
              {s.interview_questions.map((iq) => (
                <details key={iq.q} className="group py-3">
                  <summary className="cursor-pointer list-none font-medium marker:hidden">
                    <span className="mr-2 inline-block text-faint transition-transform group-open:rotate-90">›</span>{iq.q}
                  </summary>
                  <div className="mt-2 pl-5 text-muted"><Markdown>{iq.a}</Markdown></div>
                </details>
              ))}
            </div>
          </Section>
          <Section id="challenges" title="Challenges">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-line p-4">
                <p className="text-xs text-muted">Mini challenge</p>
                <p className="mt-1 font-medium">{s.mini_challenge.title}</p>
                <Markdown className="mt-1 text-sm text-muted">{s.mini_challenge.prompt}</Markdown>
                {s.mini_challenge.exercise && <Button asChild size="sm" className="mt-2"><Link to={`/challenges/${s.mini_challenge.exercise}`}>Open the exercise</Link></Button>}
              </div>
              <div className="rounded-lg border border-line p-4">
                <p className="text-xs text-muted">Advanced challenge, self-directed</p>
                <p className="mt-1 font-medium">{s.advanced_challenge.title}</p>
                <Markdown className="mt-1 text-sm text-muted">{s.advanced_challenge.prompt}</Markdown>
              </div>
            </div>
            {l.exercises.filter((e) => e.slug !== s.mini_challenge.exercise).map((e) => (
              <Link key={e.slug} to={`/challenges/${e.slug}`} className="mt-3 flex items-center justify-between rounded-lg border border-line px-4 py-3 text-sm hover:border-line-strong">
                <span><span className="text-muted">{CATEGORY_LABEL[e.category] ?? e.category} exercise: </span>{e.title}</span>
                <span className="text-muted">{e.points} points</span>
              </Link>
            ))}
          </Section>
          <Section id="reading" title="Further reading">
            <ul className="space-y-1.5">{s.further_reading.map((r) => <li key={r.url}><a href={r.url} target="_blank" rel="noreferrer noopener" className="text-signal hover:underline">{r.title}</a></li>)}</ul>
            {s.version_notes && <p className="mb-1 mt-4 text-sm text-muted"><span className="font-medium text-fg">Version notes. </span></p>}
            {s.version_notes && <Markdown className="text-sm text-muted">{s.version_notes}</Markdown>}
          </Section>
          <Section id="quiz" title="Check your understanding">
            <Quiz lesson={l} />
          </Section>
        </div>

        <footer className="mt-14 space-y-6 border-t border-line pt-6">
          {user && <CompleteButton lesson={l} />}
          <nav aria-label="Lesson navigation" className="flex flex-wrap justify-between gap-4">
            {l.navigation?.prev ? (
              <Link to={`/lessons/${l.navigation.prev.slug}`} className="group flex max-w-[48%] items-center gap-2 text-sm text-muted hover:text-fg"><ChevronLeft className="size-4" />{l.navigation.prev.title}</Link>
            ) : <span />}
            {l.navigation?.next && (
              <Link to={`/lessons/${l.navigation.next.slug}`} className="group flex max-w-[48%] items-center gap-2 text-right text-sm text-muted hover:text-fg">{l.navigation.next.title}<ChevronRight className="size-4" /></Link>
            )}
          </nav>
        </footer>
      </article>
    </div>
  );
}
