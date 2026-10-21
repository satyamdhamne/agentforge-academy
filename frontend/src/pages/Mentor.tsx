import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, LEVEL_LABEL, titleCase } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorState, PageHeader } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Markdown } from "@/components/Markdown";
import { pct } from "@/components/LabBits";

interface Cite { n: number; lesson: string; slug: string; section: string | null; quote: string }
interface Msg { role: "user" | "mentor"; content: string; citations?: Cite[] | null; context?: Record<string, string> | null }
interface Status { opted_in: boolean; stored_messages: number; privacy: string;
  assessment: { scores: Record<string, number>; recommendations: Recs; created_at: string } | null }
interface Recs { start_track: string; prerequisites: string[]; strengths: string[]; gaps: string[]; summary: string }
interface AQ { id: string; area: string; prompt: string; options: string[] }

function Chat() {
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const [message, setMessage] = useState("");
  const [lesson, setLesson] = useState(params.get("lesson") ?? "");
  const [challenge, setChallenge] = useState(params.get("challenge") ?? "");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [reveal, setReveal] = useState(false);
  const [showCtx, setShowCtx] = useState(!!(params.get("lesson") || params.get("challenge")));
  const end = useRef<HTMLDivElement>(null);
  const hist = useQuery({ queryKey: ["mentor-history"], queryFn: () => api.get<{ items: Msg[] }>("/mentor/history") });
  const [pending, setPending] = useState<Msg | null>(null);
  const ask = useMutation({
    mutationFn: () => api.post<{ reply: string; citations: Cite[]; revealed_solution: boolean }>("/mentor/ask", {
      message, lesson_slug: lesson || null, challenge_slug: challenge || null, code: code || null, error: error || null, reveal_solution: reveal }),
    onMutate: () => setPending({ role: "user", content: message }),
    onSuccess: () => { setMessage(""); setError(""); setReveal(false); qc.invalidateQueries({ queryKey: ["mentor-history"] }); qc.invalidateQueries({ queryKey: ["mentor-status"] }); },
    onError: (e) => toast.error(errorMessage(e)),
    onSettled: () => setPending(null),
  });
  const clear = useMutation({ mutationFn: () => api.delete("/mentor/history"), onSuccess: () => { qc.invalidateQueries({ queryKey: ["mentor-history"] }); toast.success("Conversation deleted"); } });
  const msgs = [...(hist.data?.items ?? []), ...(pending ? [pending] : [])];
  useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [msgs.length]);
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_16rem]">
      <div className="space-y-4">
        <div className="max-h-[60vh] min-h-48 space-y-4 overflow-y-auto rounded-lg border border-line p-4" aria-live="polite">
          {msgs.length === 0 && <p className="text-sm text-muted">Ask about a concept, paste an error, or get a hint on a challenge. The mentor answers from the course material and asks you a question back, so you do the thinking.</p>}
          {msgs.map((m, i) => (
            <div key={i} className={cn("max-w-[85%] rounded-lg px-3 py-2 text-sm", m.role === "user" ? "ml-auto bg-signal/12" : "bg-panel")}>
              {m.context && Object.keys(m.context).length > 0 && <p className="mb-1 text-xs text-faint">{Object.entries(m.context).map(([k, v]) => `${k}: ${v}`).join(", ")}</p>}
              {m.role === "mentor" ? <Markdown>{m.content}</Markdown> : <p className="whitespace-pre-wrap">{m.content}</p>}
              {!!m.citations?.length && (
                <ol className="mt-2 space-y-0.5 border-t border-line pt-2 text-xs text-muted">
                  {m.citations.map((c) => <li key={c.n}>[{c.n}] <Link className="text-signal hover:underline" to={`/lessons/${c.slug}`}>{c.lesson}</Link>{c.section && c.section.split(" › ").length > 1 ? `, ${c.section.split(" › ").slice(1).join(" › ")}` : ""}</li>)}
                </ol>
              )}
            </div>
          ))}
          {ask.isPending && <p className="text-sm text-muted">Thinking…</p>}
          <div ref={end} />
        </div>
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); ask.mutate(); }}>
          <Textarea aria-label="Message the mentor" rows={3} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Why does my loop never stop?"
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && message.trim().length >= 2) ask.mutate(); }} />
          {showCtx && (
            <div className="grid gap-3 rounded-lg border border-line p-3 md:grid-cols-2">
              <div><Label htmlFor="m-lesson">Lesson slug</Label><Input id="m-lesson" value={lesson} onChange={(e) => setLesson(e.target.value)} placeholder="js-closures" /></div>
              <div><Label htmlFor="m-challenge">Challenge slug</Label><Input id="m-challenge" value={challenge} onChange={(e) => setChallenge(e.target.value)} placeholder="py-two-sum" /></div>
              <div className="md:col-span-2"><Label htmlFor="m-code">Your code</Label><Textarea id="m-code" rows={4} className="font-mono text-xs" value={code} onChange={(e) => setCode(e.target.value)} /></div>
              <div className="md:col-span-2"><Label htmlFor="m-error">Error message</Label><Textarea id="m-error" rows={2} className="font-mono text-xs" value={error} onChange={(e) => setError(e.target.value)} /></div>
              {challenge && <label className="flex items-center gap-2 text-sm md:col-span-2"><input type="checkbox" className="accent-[var(--signal)]" checked={reveal} onChange={(e) => setReveal(e.target.checked)} />Show me the solution (only after you've attempted it)</label>}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={message.trim().length < 2 || ask.isPending}><Send />Send</Button>
            <Button type="button" variant="ghost" onClick={() => setShowCtx(!showCtx)}>{showCtx ? "Hide context" : "Add code, error or challenge"}</Button>
            {msgs.length > 0 && <Button type="button" variant="ghost" className="ml-auto" onClick={() => clear.mutate()} disabled={clear.isPending}><Trash2 />Delete conversation</Button>}
          </div>
        </form>
      </div>
      <aside className="space-y-2 text-sm text-muted">
        <p className="font-medium text-fg">How the mentor helps</p>
        <p>It cites lesson passages, explains common errors, and gives hints before answers. Full challenge solutions only appear after you've made an attempt and explicitly ask.</p>
      </aside>
    </div>
  );
}

function Assessment({ status }: { status: Status }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["mentor-assessment"], queryFn: () => api.get<{ questions: AQ[] }>("/mentor/assessment") });
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const submit = useMutation({
    mutationFn: () => api.post<{ scores: Record<string, number>; recommendations: Recs; answers: { id: string; correct: boolean; correct_index: number; explanation: string }[] }>("/mentor/assessment", { answers }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mentor-status"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!q.data) return <PageSkeleton />;
  const result = submit.data;
  const recs = result?.recommendations ?? status.assessment?.recommendations;
  const scores = result?.scores ?? status.assessment?.scores;
  const graded = Object.fromEntries((result?.answers ?? []).map((a) => [a.id, a]));
  return (
    <div className="space-y-8">
      {recs && scores && (
        <section className="space-y-4 rounded-lg border border-line bg-panel p-5">
          <p className="font-medium">{recs.summary}</p>
          <div className="flex flex-wrap gap-2"><Button asChild size="sm"><Link to={`/paths/${recs.start_track}`}>Open the {titleCase(recs.start_track.replace(/-/g, " "))} path</Link></Button></div>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries(scores).map(([a, v]) => <div key={a}><dt className="text-xs text-muted">{titleCase(a)}</dt><dd className={cn("font-display text-lg tabular-nums", v >= 0.99 ? "text-pass" : v < 0.5 ? "text-fail" : "")}>{pct(v)}</dd></div>)}
          </dl>
        </section>
      )}
      <section className="space-y-5">
        <p className="text-sm text-muted">16 quick questions, two per area. There's no penalty for guessing wrong; it only shapes the recommendations.</p>
        <ol className="space-y-5">
          {q.data.questions.map((x, i) => (
            <li key={x.id}>
              <fieldset>
                <legend className="mb-2 text-sm"><span className="mr-2 font-mono text-faint">{i + 1}</span><Badge tone="outline" className="mr-2">{titleCase(x.area)}</Badge><Markdown className="inline [&>p]:inline">{x.prompt}</Markdown></legend>
                <div className="flex flex-wrap gap-2">
                  {x.options.map((o, k) => {
                    const g = graded[x.id];
                    return (
                      <label key={k} className={cn("flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm",
                        g ? (k === g.correct_index ? "border-pass/60" : answers[x.id] === k ? "border-fail/60" : "border-line") : answers[x.id] === k ? "border-signal" : "border-line hover:border-line-strong")}>
                        <input type="radio" name={x.id} className="accent-[var(--signal)]" checked={answers[x.id] === k} onChange={() => setAnswers({ ...answers, [x.id]: k })} disabled={!!g} />{o}
                      </label>
                    );
                  })}
                </div>
                {graded[x.id] && <p className="mt-1 text-xs text-muted">{graded[x.id].explanation}</p>}
              </fieldset>
            </li>
          ))}
        </ol>
        {result ? <Button variant="secondary" onClick={() => { submit.reset(); setAnswers({}); }}>Retake</Button> :
          <Button onClick={() => submit.mutate()} disabled={submit.isPending || Object.keys(answers).length < q.data.questions.length}>See my recommendations</Button>}
      </section>
    </div>
  );
}

function NextSteps() {
  const q = useQuery({ queryKey: ["mentor-recs"], queryFn: () => api.get<{ target_difficulty: string; success_by_difficulty: Record<string, number>; weak_categories: string[];
    challenges: { slug: string; title: string; category: string; difficulty: string; points: number }[]; next_lesson: { slug: string; title: string } | null; reason: string }>("/mentor/recommendations") });
  if (q.error) return <ErrorState error={q.error} />;
  if (!q.data) return <PageSkeleton />;
  const d = q.data;
  return (
    <div className="space-y-6">
      <p>Next difficulty: <span className="font-medium">{LEVEL_LABEL[d.target_difficulty] ?? d.target_difficulty}</span>. <span className="text-muted">{d.reason}</span>
        {d.weak_categories.length > 0 && <span className="text-muted"> Practice focuses on {d.weak_categories.map((c) => c.replace(/_/g, " ")).join(" and ")}.</span>}</p>
      {d.next_lesson && <p className="text-sm">Next unread lesson: <Link className="text-signal hover:underline" to={`/lessons/${d.next_lesson.slug}`}>{d.next_lesson.title}</Link></p>}
      <ul className="grid gap-2 md:grid-cols-2">
        {d.challenges.map((c) => (
          <li key={c.slug}><Link to={`/challenges/${c.slug}`} className="block rounded-lg border border-line p-3 hover:border-line-strong hover:bg-panel">
            <span className="font-medium">{c.title}</span><span className="mt-1 block text-xs text-muted">{c.category.replace(/_/g, " ")}, {c.points} points</span></Link></li>
        ))}
      </ul>
      {d.challenges.length === 0 && <p className="text-sm text-muted">You've solved every free challenge at this level. Nice work.</p>}
    </div>
  );
}

export default function Mentor() {
  const { refresh } = useAuth();
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["mentor-status"], queryFn: () => api.get<Status>("/mentor/status") });
  const optIn = useMutation({
    mutationFn: (on: boolean) => api.patch("/me/profile", { mentor_opt_in: on }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["mentor-status"] }); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (status.error) return <ErrorState error={status.error} />;
  if (!status.data) return <PageSkeleton />;
  const s = status.data;
  return (
    <div>
      <PageHeader title="AI Mentor" description="A Socratic study partner grounded in the course: hints before answers, citations for every explanation, and next steps that adapt to how you're doing."
        actions={s.opted_in ? <Button variant="ghost" onClick={() => optIn.mutate(false)} disabled={optIn.isPending}>Turn off</Button> : undefined} />
      {!s.opted_in ? (
        <section className="max-w-2xl space-y-4 rounded-lg border border-line p-6">
          <Sparkles className="size-6 text-llm" />
          <p className="font-display text-lg font-semibold">The mentor is opt-in</p>
          <p className="text-muted">{s.privacy}</p>
          <Button onClick={() => optIn.mutate(true)} disabled={optIn.isPending}>Turn on the mentor</Button>
          <p className="text-xs text-faint">You can switch it off here or in Settings at any time.</p>
        </section>
      ) : (
        <Tabs defaultValue="chat">
          <TabsList><TabsTrigger value="chat">Ask</TabsTrigger><TabsTrigger value="assessment">Skill check</TabsTrigger><TabsTrigger value="next">Next steps</TabsTrigger></TabsList>
          <TabsContent value="chat"><Chat /></TabsContent>
          <TabsContent value="assessment"><Assessment status={s} /></TabsContent>
          <TabsContent value="next"><NextSteps /></TabsContent>
        </Tabs>
      )}
    </div>
  );
}
