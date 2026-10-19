import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, Lightbulb, Lock, RotateCcw, Send, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Attempt, ChallengeDetail } from "@/lib/types";
import { CATEGORY_LABEL, cn, formatDate, titleCase } from "@/lib/utils";
import { Markdown } from "@/components/Markdown";
import { CodeEditor } from "@/components/LazyEditor";
import { CodeBlock } from "@/components/CodeBlock";
import { SqlTable } from "@/components/CodeRunner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/input";
import { ErrorState, EmptyState } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { LevelPips } from "@/components/Meta";

const STATUS_COPY: Record<Attempt["status"], { label: string; tone: "pass" | "fail" | "tool" | "neutral" }> = {
  passed: { label: "Passed", tone: "pass" },
  failed: { label: "Not yet", tone: "fail" },
  error: { label: "Error", tone: "fail" },
  not_graded: { label: "Saved, not graded", tone: "tool" },
  pending_review: { label: "Waiting for review", tone: "tool" },
  reviewed: { label: "Reviewed", tone: "pass" },
};

const show = (v: unknown) => (typeof v === "string" ? JSON.stringify(v) : JSON.stringify(v));

function draftKey(slug: string) { return `af-draft:${slug}`; }
function loadDraft(slug: string): string | null { try { return localStorage.getItem(draftKey(slug)); } catch { return null; } }
function saveDraft(slug: string, v: string) { try { localStorage.setItem(draftKey(slug), v); } catch { /* storage unavailable */ } }

function Timer({ minutes }: { minutes: number }) {
  const [started, setStarted] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { if (!started) return; const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, [started]);
  if (!started) return <Button size="sm" variant="secondary" onClick={() => { setStarted(Date.now()); setNow(Date.now()); }}><Clock />Start {minutes}-minute timer</Button>;
  const left = Math.max(0, minutes * 60 - Math.floor((now - started) / 1000));
  const mm = String(Math.floor(left / 60)).padStart(2, "0"), ss = String(left % 60).padStart(2, "0");
  return <span role="timer" className={cn("inline-flex items-center gap-1.5 font-mono text-sm tabular-nums", left < 120 ? "text-fail" : "text-muted")}><Clock className="size-4" />{mm}:{ss}{left === 0 && " - time’s up"}</span>;
}

function AttemptResult({ a, c }: { a: Attempt; c: ChallengeDetail }) {
  const s = STATUS_COPY[a.status];
  const r = a.result;
  return (
    <div className="space-y-3 rounded-lg border border-line bg-panel p-4" aria-live="polite">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone={s.tone} className="text-sm">{s.label}</Badge>
        {r.tests_total ? <span className="text-sm tabular-nums text-muted">{r.tests_passed}/{r.tests_total} tests</span> : null}
        {a.points_awarded > 0 && <span className="text-sm font-medium text-pass">+{a.points_awarded} points</span>}
        {a.duplicate && <span className="text-xs text-muted">Same submission as before - showing the earlier result.</span>}
        {typeof r.duration_ms === "number" && <span className="ml-auto text-xs text-faint">{r.duration_ms} ms in the sandbox</span>}
      </div>
      {r.message && <p className="text-sm text-muted">{r.message}</p>}
      {r.compile_error && <pre className="overflow-x-auto rounded bg-sunken p-3 font-mono text-xs whitespace-pre-wrap text-fail">{r.compile_error}</pre>}
      {r.timed_out && <p className="text-sm text-fail">Your code hit the time limit. Look for an infinite loop or an O(n²) step.</p>}
      {r.results && r.results.length > 0 && (
        <ul className="divide-y divide-line rounded-md border border-line font-mono text-xs">
          {r.results.map((t) => (
            <li key={t.index} className="flex gap-2 px-3 py-2">
              {t.passed ? <CheckCircle2 className="size-4 shrink-0 text-pass" /> : <XCircle className="size-4 shrink-0 text-fail" />}
              {t.hidden ? (
                <span className="text-muted">Hidden test {t.index + 1} {t.passed ? "passed" : "failed"}{t.error ? ` (${t.error})` : ""}</span>
              ) : c.language === "sql" ? (
                <span className="text-muted">Result set {t.passed ? "matches" : "doesn’t match"} the expected rows</span>
              ) : (
                <span className="min-w-0 break-all">
                  <span className="text-muted">args </span>{show(t.args)}
                  <span className="text-muted"> expected </span>{show(t.expected)}
                  {!t.passed && <><span className="text-muted"> got </span><span className="text-fail">{t.error ?? show(t.actual)}</span></>}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {r.sql && r.sql.columns.length > 0 && <div className="rounded-md border border-line"><SqlTable columns={r.sql.columns} rows={r.sql.rows} /></div>}
      {r.stdout && <details><summary className="cursor-pointer text-xs text-muted">Printed output</summary><pre className="mt-1 max-h-48 overflow-auto rounded bg-sunken p-3 font-mono text-xs">{r.stdout}</pre></details>}
      {a.review_feedback && <div className="rounded-md border border-line p-3 text-sm"><p className="mb-1 text-xs text-muted">Reviewer feedback</p>{a.review_feedback}</div>}
    </div>
  );
}

export default function ChallengeWorkspace() {
  const { slug = "" } = useParams();
  const { user } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["challenge", slug], queryFn: () => api.get<ChallengeDetail>(`/challenges/${slug}`) });
  const attempts = useQuery({ queryKey: ["attempts", slug], queryFn: () => api.get<{ items: Attempt[] }>(`/challenges/${slug}/attempts`), enabled: !!user });
  const c = q.data;
  const [code, setCode] = useState<string>("");
  const [choice, setChoice] = useState<number | null>(null);
  const [essay, setEssay] = useState("");
  const [last, setLast] = useState<Attempt | null>(null);

  useEffect(() => {
    if (!c || c.locked) return;
    const d = loadDraft(slug);
    if (c.kind === "manual_review") setEssay(d ?? "");
    else setCode(d ?? c.starter_code);
    setLast(null);
  }, [c?.slug]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = useMutation({
    mutationFn: () => api.post<Attempt>(`/challenges/${slug}/attempts`,
      c!.kind === "code" ? { code } : c!.kind === "multiple_choice" ? { selected_index: choice } : { answer_text: essay },
      { headers: { "Idempotency-Key": crypto.randomUUID() } }),
    onSuccess: (a) => {
      setLast(a);
      a.new_achievements?.forEach((x) => toast(`Achievement unlocked: ${x.name}`));
      qc.invalidateQueries({ queryKey: ["challenge", slug] });
      qc.invalidateQueries({ queryKey: ["attempts", slug] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const hint = useMutation({
    mutationFn: (i: number) => api.post<{ text: string; points_available: number }>(`/challenges/${slug}/hints/${i}`),
    onSuccess: (h) => { toast(`Hint revealed. This challenge is now worth up to ${h.points_available} points.`); qc.invalidateQueries({ queryKey: ["challenge", slug] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const words = useMemo(() => essay.trim().split(/\s+/).filter(Boolean).length, [essay]);

  if (q.isLoading) return <PageSkeleton />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!c) return null;
  if (c.locked)
    return <EmptyState title={`${c.title} is a Pro challenge`} action={<Button asChild><Link to="/pricing"><Lock />See plans</Link></Button>}>Upgrade to attempt expert challenges and get them reviewed.</EmptyState>;

  const canSubmit = !!user && (c.kind === "code" ? code.trim().length > 0 : c.kind === "multiple_choice" ? choice !== null : words >= (c.min_words ?? 50));
  const nextHint = c.hints.length;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
      <section aria-label="Challenge" className="min-w-0 space-y-6">
        <div>
          <Link to="/challenges" className="text-sm text-muted hover:text-fg">Challenges</Link>
          <h1 className="mt-2 text-3xl font-semibold leading-tight">{c.title}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted">
            <LevelPips level={c.difficulty} />
            <span>{CATEGORY_LABEL[c.category] ?? c.category}</span>
            <span>{c.points} points</span>
            {c.solved && <span className="inline-flex items-center gap-1 text-pass"><CheckCircle2 className="size-4" />Solved, {c.points_earned} earned</span>}
            {c.time_limit_minutes && <Timer minutes={c.time_limit_minutes} />}
          </div>
        </div>
        <Markdown>{c.prompt_md}</Markdown>

        {c.kind === "code" && c.language !== "sql" && c.public_tests.length > 0 && (
          <div>
            <h2 className="mb-2 text-sm font-medium">Example tests</h2>
            <ul className="space-y-1 rounded-md border border-line bg-sunken p-3 font-mono text-xs">
              {c.public_tests.map((t, i) => <li key={i} className="break-all"><span className="text-muted">args</span> {show(t.args)} <span className="text-muted">→</span> {show(t.expected)}</li>)}
            </ul>
            {c.hidden_tests > 0 && <p className="mt-1.5 text-xs text-faint">Plus {c.hidden_tests} hidden {c.hidden_tests === 1 ? "test" : "tests"}, so hard-coding the examples won’t pass.</p>}
          </div>
        )}
        {c.sql_setup && (
          <details>
            <summary className="cursor-pointer text-sm font-medium">Database setup</summary>
            <CodeBlock code={c.sql_setup} language="sql" className="mt-2" />
          </details>
        )}
        {c.rubric && (
          <div>
            <h2 className="mb-2 text-sm font-medium">How a reviewer will score this</h2>
            <ul className="divide-y divide-line rounded-md border border-line text-sm">
              {c.rubric.map((r) => (
                <li key={r.criterion} className="px-3 py-2">
                  <span className="font-medium">{titleCase(r.criterion)}</span>
                  {r.weight && <span className="ml-2 text-xs text-muted">weight {r.weight}</span>}
                  <p className="text-muted">{r.description}</p>
                </li>
              ))}
            </ul>
          </div>
        )}

        {c.hints_total > 0 && (
          <div>
            <h2 className="mb-2 text-sm font-medium">Hints</h2>
            <ol className="space-y-2">
              {c.hints.map((h) => <li key={h.index} className="flex gap-2 rounded-md border border-tool/30 bg-tool/5 px-3 py-2 text-sm"><Lightbulb className="mt-0.5 size-4 shrink-0 text-tool" /><Markdown className="[&_p]:m-0">{h.text}</Markdown></li>)}
            </ol>
            {nextHint < c.hints_total && user && (
              <Button size="sm" variant="ghost" className="mt-2" onClick={() => hint.mutate(nextHint)} disabled={hint.isPending}>
                <Lightbulb />Reveal hint {nextHint + 1} of {c.hints_total} (−20% points)
              </Button>
            )}
          </div>
        )}

        {(c.explanation_md || last?.explanation_md) && (
          <div className="rounded-lg border border-pass/30 bg-pass/5 p-4">
            <h2 className="mb-2 font-medium">Explanation</h2>
            <Markdown>{c.explanation_md || last?.explanation_md}</Markdown>
            {(c.solution || last?.solution) && (
              <details className="mt-3"><summary className="cursor-pointer text-sm text-muted">Reference solution</summary>
                <CodeBlock className="mt-2" code={(c.solution || last?.solution)!} language={c.language ?? "text"} />
              </details>
            )}
          </div>
        )}
      </section>

      <section aria-label="Your answer" className="min-w-0 space-y-4 lg:sticky lg:top-20 lg:self-start">
        {c.kind === "code" && (
          <>
            <div className="flex items-center gap-2 text-sm">
              <Badge tone="outline">{c.language}</Badge>
              {c.execution === "sandbox" ? <span className="text-muted">Graded in an isolated sandbox with CPU, memory and time limits</span>
                : <span className="text-tool">Secure code execution isn’t configured on this server. Submissions are saved but not graded.</span>}
              <Button size="sm" variant="ghost" className="ml-auto" onClick={() => { setCode(c.starter_code); saveDraft(slug, c.starter_code); }}><RotateCcw />Reset</Button>
            </div>
            <CodeEditor value={code} language={c.language ?? "python"} height={440} onChange={(v) => { setCode(v); saveDraft(slug, v); }} onRun={() => canSubmit && submit.mutate()} ariaLabel="Solution editor" />
          </>
        )}
        {c.kind === "multiple_choice" && c.options && (
          <fieldset className="space-y-2">
            <legend className="mb-2 text-sm font-medium">Choose one</legend>
            {c.options.map((o, i) => (
              <label key={i} className={cn("flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2.5 text-sm", choice === i ? "border-signal bg-signal/5" : "border-line hover:border-line-strong")}>
                <input type="radio" name="choice" className="mt-1 accent-[var(--signal)]" checked={choice === i} onChange={() => setChoice(i)} />
                <span>{o}</span>
              </label>
            ))}
            <p className="text-xs text-faint">Wrong guesses reduce the points for this question.</p>
          </fieldset>
        )}
        {c.kind === "manual_review" && (
          <div>
            <Textarea aria-label="Your answer" rows={18} value={essay} onChange={(e) => { setEssay(e.target.value); saveDraft(slug, e.target.value); }}
              placeholder="Write your answer in Markdown. Diagrams in Mermaid or ASCII are welcome." className="font-mono text-[13px]" disabled={c.pending_review} />
            <p className={cn("mt-1 text-xs", words >= (c.min_words ?? 50) ? "text-muted" : "text-faint")}>{words} / {c.min_words ?? 50} words minimum. A reviewer scores it against the rubric.</p>
          </div>
        )}
        {user ? (
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => submit.mutate()} disabled={!canSubmit || submit.isPending || c.pending_review}>
              <Send />{submit.isPending ? (c.kind === "code" ? "Running tests…" : "Submitting…") : c.kind === "manual_review" ? "Submit for review" : c.kind === "code" ? "Submit and run tests" : "Submit answer"}
            </Button>
            {c.kind === "code" && <span className="text-xs text-faint">Ctrl/⌘ + Enter</span>}
            {c.pending_review && <span className="text-sm text-tool">Your submission is waiting for a reviewer.</span>}
          </div>
        ) : (
          <p className="text-sm text-muted"><Link className="text-signal hover:underline" to={`/login?next=/challenges/${slug}`}>Sign in</Link> to submit and earn points.</p>
        )}
        {last && <AttemptResult a={last} c={c} />}
        {attempts.data && attempts.data.items.length > 0 && (
          <details>
            <summary className="cursor-pointer text-sm text-muted">Your attempts ({attempts.data.items.length})</summary>
            <ul className="mt-2 divide-y divide-line rounded-md border border-line text-sm">
              {attempts.data.items.map((a) => (
                <li key={a.id} className="flex items-center gap-3 px-3 py-2">
                  <Badge tone={STATUS_COPY[a.status].tone}>{STATUS_COPY[a.status].label}</Badge>
                  <span className="text-muted">{formatDate(a.created_at)}</span>
                  {a.points_awarded > 0 && <span className="ml-auto text-pass">+{a.points_awarded}</span>}
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>
    </div>
  );
}
