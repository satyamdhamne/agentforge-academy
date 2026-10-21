import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleDashed, Mic } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, formatDate, LEVEL_LABEL, titleCase } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label, Select, Textarea } from "@/components/ui/input";
import { ErrorState, PageHeader } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Markdown } from "@/components/Markdown";
import { pct } from "@/components/LabBits";

interface Track { slug: string; title: string; questions: number }
interface Q { id: string; track: string; difficulty: string; prompt: string; concise_answer?: string; explanation?: string; example?: string;
  follow_ups?: string[]; common_mistakes?: string[]; key_points?: string[] }
type Scores = Record<string, number>;
interface Feedback { [k: string]: unknown; covered?: string[]; missed?: string[]; scorer?: string }
interface SessionOut { id: string; track: string; status: string; scorer: string; overall: number | null; disclaimer: string;
  summary: { criteria: Scores; answered: number; of: number; focus_next: string; tip: string } | null;
  items: { question: Q; answer: { text: string; scores: Scores; feedback: Feedback; overall: number } | null }[] }

const CRITERIA: Record<string, string> = { technical_accuracy: "Technical accuracy", reasoning: "Reasoning", tradeoffs: "Trade-offs", communication: "Communication" };

function ScoreBars({ scores }: { scores: Scores }) {
  return (
    <dl className="space-y-1.5">
      {Object.entries(CRITERIA).map(([k, l]) => (
        <div key={k} className="grid grid-cols-[9rem_1fr_3rem] items-center gap-3 text-sm">
          <dt className="text-muted">{l}</dt>
          <dd className="h-2 overflow-hidden rounded-full bg-panel-2"><span className={cn("block h-full rounded-full", (scores[k] ?? 0) >= 0.7 ? "bg-pass" : (scores[k] ?? 0) >= 0.4 ? "bg-tool" : "bg-fail")} style={{ width: `${(scores[k] ?? 0) * 100}%` }} /></dd>
          <dd className="text-right tabular-nums">{pct(scores[k])}</dd>
        </div>
      ))}
    </dl>
  );
}

function Reference({ q }: { q: Q }) {
  return (
    <div className="space-y-4 text-sm">
      {q.concise_answer && <div><p className="mb-1 font-medium">Concise answer</p><p>{q.concise_answer}</p></div>}
      {q.explanation && <div><p className="mb-1 font-medium">Explanation</p><Markdown>{q.explanation}</Markdown></div>}
      {q.example && <div><p className="mb-1 font-medium">Example</p><Markdown>{q.example}</Markdown></div>}
      {!!q.key_points?.length && <div><p className="mb-1 font-medium">Key points interviewers listen for</p><ul className="list-disc pl-5">{q.key_points.map((k) => <li key={k}>{k}</li>)}</ul></div>}
      {!!q.common_mistakes?.length && <div><p className="mb-1 font-medium">Common mistakes</p><ul className="list-disc pl-5 text-muted">{q.common_mistakes.map((k) => <li key={k}>{k}</li>)}</ul></div>}
      {!!q.follow_ups?.length && <div><p className="mb-1 font-medium">Likely follow-ups</p><ul className="list-disc pl-5 text-muted">{q.follow_ups.map((k) => <li key={k}>{k}</li>)}</ul></div>}
    </div>
  );
}

export function InterviewsHome() {
  const { user } = useAuth();
  const t = useQuery({ queryKey: ["interview-tracks"], queryFn: () => api.get<{ items: Track[]; rubric: { criterion: string; weight: number }[]; disclaimer: string }>("/interviews/tracks") });
  const s = useQuery({ queryKey: ["interview-sessions"], queryFn: () => api.get<{ items: { id: string; track: string; status: string; overall: number | null; questions: number; created_at: string }[] }>("/interviews/sessions"), enabled: !!user });
  if (t.error) return <ErrorState error={t.error} />;
  if (!t.data) return <PageSkeleton />;
  const titles = Object.fromEntries(t.data.items.map((x) => [x.slug, x.title]));
  return (
    <div className="space-y-10">
      <PageHeader title="Interview Arena" description="Practise technical interview questions across 19 tracks, then take a timed-free mock interview scored against a transparent rubric." />
      <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {t.data.items.map((tr) => (
            <li key={tr.slug}><Link to={`/interviews/${tr.slug}`} className="flex h-full items-center justify-between gap-2 rounded-lg border border-line px-4 py-3 hover:border-line-strong hover:bg-panel">
              <span className="font-medium">{tr.title}</span><span className="text-xs text-muted">{tr.questions} questions</span></Link></li>
          ))}
        </ul>
        <aside className="space-y-3 text-sm">
          <h2 className="font-display text-base font-semibold">How answers are scored</h2>
          <ul className="space-y-1">{t.data.rubric.map((r) => <li key={r.criterion} className="flex justify-between"><span>{CRITERIA[r.criterion]}</span><span className="tabular-nums text-muted">{Math.round(r.weight * 100)}%</span></li>)}</ul>
          <p className="text-xs text-faint">{t.data.disclaimer}</p>
        </aside>
      </section>
      {user && !!s.data?.items.length && (
        <section>
          <h2 className="mb-3 font-display text-lg font-semibold">Your mock interviews</h2>
          <ul className="divide-y divide-line rounded-lg border border-line">
            {s.data.items.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm">
                <Link to={`/interviews/session/${x.id}`} className="flex-1 font-medium hover:text-signal">{titles[x.track] ?? x.track}</Link>
                <Badge tone={x.status === "completed" ? "pass" : "outline"}>{x.status === "completed" ? "completed" : "in progress"}</Badge>
                <span className="w-14 text-right tabular-nums">{pct(x.overall)}</span><span className="w-28 text-right text-xs text-muted">{formatDate(x.created_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export function InterviewTrack() {
  const { track } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const [difficulty, setDifficulty] = useState("");
  const [count, setCount] = useState(3);
  const q = useQuery({ queryKey: ["interview-questions", track], queryFn: () => api.get<{ title: string; items: Q[] }>("/interviews/questions", { params: { track } }) });
  const start = useMutation({
    mutationFn: () => api.post<{ id: string }>("/interviews/sessions", { track, count, difficulty: difficulty || null }),
    onSuccess: (s) => nav(`/interviews/session/${s.id}`),
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (q.error) return <ErrorState error={q.error} />;
  if (!q.data) return <PageSkeleton />;
  const levels = [...new Set(q.data.items.map((x) => x.difficulty))];
  return (
    <div className="space-y-8">
      <div>
        <Link to="/interviews" className="text-sm text-muted hover:text-fg">Interview Arena</Link>
        <h1 className="mt-2 text-3xl font-semibold">{q.data.title}</h1>
      </div>
      <section className="flex flex-wrap items-end gap-3 rounded-lg border border-line p-4">
        <div className="mr-auto"><p className="font-medium">Mock interview</p><p className="text-sm text-muted">Questions are picked at random and answers stay hidden until you submit yours.</p></div>
        <div><Label htmlFor="mi-level">Difficulty</Label><Select id="mi-level" value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
          <option value="">Mixed</option>{levels.map((l) => <option key={l} value={l}>{LEVEL_LABEL[l] ?? titleCase(l)}</option>)}</Select></div>
        <div><Label htmlFor="mi-count">Questions</Label><Select id="mi-count" value={count} onChange={(e) => setCount(Number(e.target.value))}>{[1, 2, 3, 4].map((n) => <option key={n}>{n}</option>)}</Select></div>
        {user ? <Button onClick={() => start.mutate()} disabled={start.isPending}><Mic />Start</Button>
          : <Button asChild variant="secondary"><Link to={`/login?next=/interviews/${track}`}>Sign in to start</Link></Button>}
      </section>
      <section>
        <h2 className="mb-3 font-display text-lg font-semibold">Practice questions</h2>
        <ul className="divide-y divide-line rounded-lg border border-line">
          {q.data.items.map((x) => (
            <li key={x.id}>
              <details className="group p-4">
                <summary className="flex cursor-pointer items-start gap-3">
                  <Badge tone="outline" className="mt-0.5">{LEVEL_LABEL[x.difficulty] ?? x.difficulty}</Badge>
                  <span className="flex-1"><Markdown>{x.prompt}</Markdown></span>
                  <span className="text-xs text-muted group-open:hidden">Show answer</span>
                </summary>
                <div className="mt-4 border-t border-line pt-4"><Reference q={x} /></div>
              </details>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export function InterviewSession() {
  const { id } = useParams();
  const qc = useQueryClient();
  const s = useQuery({ queryKey: ["interview-session", id], queryFn: () => api.get<SessionOut>(`/interviews/sessions/${id}`) });
  const tracks = useQuery({ queryKey: ["interview-tracks"], queryFn: () => api.get<{ items: Track[] }>("/interviews/tracks") });
  const [idx, setIdx] = useState<number | null>(null);
  const [text, setText] = useState("");
  const submit = useMutation({
    mutationFn: (qid: string) => api.post(`/interviews/sessions/${id}/answers`, { question_id: qid, answer_text: text }),
    onSuccess: () => { setText(""); qc.invalidateQueries({ queryKey: ["interview-session", id] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const finish = useMutation({
    mutationFn: () => api.post(`/interviews/sessions/${id}/finish`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["interview-session", id] }); qc.invalidateQueries({ queryKey: ["interview-sessions"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (s.error) return <ErrorState error={s.error} />;
  if (!s.data) return <PageSkeleton />;
  const d = s.data;
  const firstOpen = d.items.findIndex((i) => !i.answer);
  const current = idx ?? (firstOpen === -1 ? 0 : firstOpen);
  const item = d.items[current];
  const answered = d.items.filter((i) => i.answer).length;
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  return (
    <div className="space-y-8">
      <div>
        <Link to={`/interviews/${d.track}`} className="text-sm text-muted hover:text-fg">{tracks.data?.items.find((t) => t.slug === d.track)?.title ?? titleCase(d.track.replace(/-/g, " "))}</Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-semibold">Mock interview</h1>
          <Badge tone="outline">{d.scorer === "model" ? "Model-graded with rubric check" : "Rubric-scored"}</Badge>
          <span className="text-sm text-muted">{answered} of {d.items.length} answered</span>
        </div>
      </div>

      {d.status === "completed" && d.summary && (
        <section className="space-y-4 rounded-lg border border-line bg-panel p-5">
          <div className="flex flex-wrap items-baseline gap-3"><h2 className="font-display text-xl font-semibold">Result</h2><span className="font-display text-3xl tabular-nums">{pct(d.overall)}</span>
            <span className="text-sm text-muted">{d.summary.answered} of {d.summary.of} questions answered</span></div>
          <ScoreBars scores={d.summary.criteria} />
          <p className="text-sm"><span className="font-medium">Focus next: {CRITERIA[d.summary.focus_next]}.</span> {d.summary.tip}</p>
          <p className="text-xs text-faint">{d.disclaimer}</p>
        </section>
      )}

      <nav className="flex flex-wrap gap-2" aria-label="Questions">
        {d.items.map((i, n) => (
          <button key={i.question.id} onClick={() => setIdx(n)} aria-current={n === current}
            className={cn("inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm", n === current ? "border-signal text-fg" : "border-line text-muted hover:text-fg")}>
            {i.answer ? <CheckCircle2 className="size-4 text-pass" /> : <CircleDashed className="size-4" />}Question {n + 1}
          </button>
        ))}
      </nav>

      {item && (
        <section className="space-y-5">
          <div className="flex items-start gap-3"><Badge tone="outline" className="mt-1">{LEVEL_LABEL[item.question.difficulty] ?? item.question.difficulty}</Badge>
            <div className="text-lg"><Markdown>{item.question.prompt}</Markdown></div></div>
          {!item.answer && d.status === "in_progress" ? (
            <div className="space-y-3">
              <Textarea aria-label="Your answer" rows={9} value={text} onChange={(e) => setText(e.target.value)} placeholder="Answer as you would out loud: lead with the answer, explain why, give an example, and name the trade-offs." />
              <div className="flex flex-wrap items-center gap-3">
                <Button onClick={() => { setIdx(current); submit.mutate(item.question.id); }} disabled={words < 3 || submit.isPending}>{submit.isPending ? "Scoring…" : "Submit answer"}</Button>
                <span className={cn("text-xs", words > 250 ? "text-tool" : "text-muted")}>{words} words{words > 250 ? ": aim for under 250" : ""}</span>
                {answered > 0 && <Button variant="ghost" className="ml-auto" onClick={() => finish.mutate()} disabled={finish.isPending}>Finish interview</Button>}
              </div>
            </div>
          ) : item.answer ? (
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="space-y-4">
                <div><p className="mb-1 text-sm font-medium">Your answer</p><p className="whitespace-pre-wrap rounded-md bg-sunken p-3 text-sm">{item.answer.text}</p></div>
                <div className="flex items-baseline gap-3"><span className="font-display text-2xl tabular-nums">{pct(item.answer.overall)}</span><span className="text-sm text-muted">overall for this answer</span></div>
                <ScoreBars scores={item.answer.scores} />
                <ul className="space-y-2 text-sm">
                  {Object.entries(CRITERIA).map(([k, l]) => typeof item.answer!.feedback[k] === "string" && <li key={k}><span className="font-medium">{l}:</span> <span className="text-muted">{item.answer!.feedback[k] as string}</span></li>)}
                </ul>
                {d.status === "in_progress" && (
                  <div className="flex gap-2">
                    {firstOpen !== -1 && <Button onClick={() => setIdx(firstOpen)}>Next question</Button>}
                    <Button variant={firstOpen === -1 ? "primary" : "ghost"} onClick={() => finish.mutate()} disabled={finish.isPending}>Finish interview</Button>
                  </div>
                )}
              </div>
              <div className="rounded-lg border border-line p-4"><p className="mb-3 font-display text-base font-semibold">Reference</p><Reference q={item.question} /></div>
            </div>
          ) : <p className="text-sm text-muted">Not answered.</p>}
        </section>
      )}
      <p className="text-xs text-faint">{d.disclaimer}</p>
    </div>
  );
}
