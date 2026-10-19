import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Check, GitPullRequest, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AgentDetail, ExerciseCard, Paged, AgentCard, TrackSummary } from "@/lib/types";
import { CATEGORY_LABEL, VERDICT_HELP, VERDICT_LABEL, cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { TraceView } from "@/components/TraceView";
import { Logo } from "@/components/layout/Logo";
import { TopBarActions } from "@/components/layout/AppShell";
import { CommandPalette, useCommandPalette } from "@/components/layout/CommandPalette";
import { LevelPips } from "@/components/Meta";

/* Stages group the 16 tracks into the order most engineers take them. */
const STAGES: { name: string; tracks: string[] }[] = [
  { name: "Foundations", tracks: ["cs-fundamentals", "javascript-typescript", "python"] },
  { name: "Product engineering", tracks: ["react", "angular", "nodejs", "fastapi", "databases"] },
  { name: "Production systems", tracks: ["aws-devops", "system-design"] },
  { name: "AI engineering", tracks: ["generative-ai", "rag-engineering", "agentic-ai", "llm-slm-engineering", "ai-security"] },
  { name: "Get hired", tracks: ["ai-interviews"] },
];

const SEVERITY_TONE: Record<string, "fail" | "tool" | "neutral"> = { high: "fail", medium: "tool", low: "neutral", info: "neutral" };

function HeroRun() {
  const q = useQuery({ queryKey: ["agent", "github-pr-review-agent"], queryFn: () => api.get<AgentDetail>("/agents/github-pr-review-agent") });
  const [replay, setReplay] = useState(0);
  const run = q.data?.example_runs?.[0];
  const out = run?.output as { verdict?: string; summary?: string; comments?: { rule: string; line: number | null; severity: string; message: string }[] } | undefined;
  return (
    <div className="relative rounded-xl border border-line bg-panel shadow-[0_30px_80px_-40px_rgba(0,0,0,.6)]">
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5 text-sm">
        <GitPullRequest className="size-4 text-signal" />
        <span className="font-medium">PR Review Agent</span>
        <span className="truncate text-muted">reviewing “{String(run?.input?.title ?? "Add CRM sync")}”</span>
        <button onClick={() => setReplay((n) => n + 1)} className="ml-auto shrink-0 text-xs text-muted hover:text-fg" disabled={!run}>Replay</button>
      </div>
      <div className="space-y-4 p-4">
        {run ? (
          <TraceView key={replay} spans={run.trace} animate compact />
        ) : (
          <div className="h-32 animate-pulse rounded bg-panel-2" />
        )}
        {out && (
          <div className="rounded-lg border border-line bg-sunken p-3">
            <div className="mb-2 flex items-center gap-2 text-sm">
              <ShieldAlert className="size-4 text-fail" />
              <span className="font-medium">{out.verdict === "request_changes" ? "Changes requested" : "Approved"}</span>
              <span className="ml-auto text-xs text-muted tabular-nums">{run?.input_tokens} in / {run?.output_tokens} out tokens</span>
            </div>
            <ul className="space-y-1.5 text-[13px]">
              {out.comments?.slice(0, 3).map((c) => (
                <li key={c.rule} className="flex gap-2">
                  <Badge tone={SEVERITY_TONE[c.severity]} className="mt-0.5 w-14 justify-center">{c.severity}</Badge>
                  <span className="min-w-0"><span className="font-mono text-xs text-muted">{c.line ? `L${c.line} ` : ""}</span>{c.message}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="text-xs text-faint">
          A recorded run of a reference agent from the library: deterministic rules first, one model call to prioritise, guardrails last.
          Replayed with the mock provider, so no API key is needed.
        </p>
      </div>
    </div>
  );
}

function Roadmap() {
  const q = useQuery({ queryKey: ["tracks"], queryFn: () => api.get<{ items: TrackSummary[] }>("/tracks") });
  const by = new Map(q.data?.items.map((t) => [t.slug, t]));
  return (
    <ol className="grid gap-6 md:grid-cols-5">
      {STAGES.map((s, i) => (
        <li key={s.name} className="relative">
          <div className="mb-3 flex items-center gap-2">
            <span className="grid size-6 place-items-center rounded-full border border-line-strong font-mono text-xs text-muted">{i + 1}</span>
            <span className="font-display font-semibold">{s.name}</span>
          </div>
          <ul className="space-y-1.5 border-l border-line pl-4">
            {s.tracks.map((slug) => {
              const t = by.get(slug);
              return (
                <li key={slug}>
                  <Link to={`/paths/${slug}`} className="group block rounded py-0.5 text-sm text-muted hover:text-fg">
                    {t?.title ?? slug}
                    {t && <span className="ml-1.5 text-xs text-faint">{t.lessons_total} lessons</span>}
                  </Link>
                </li>
              );
            })}
          </ul>
        </li>
      ))}
    </ol>
  );
}

function VerdictSplit() {
  const q = useQuery({ queryKey: ["agents", {}], queryFn: () => api.get<Paged<AgentCard> & { facets: { verdicts: Record<string, number> } }>("/agents") });
  const v = (q.data as unknown as { facets?: { verdicts: Record<string, number> } })?.facets?.verdicts ?? {};
  const total = Object.values(v).reduce((a, b) => a + b, 0) || 100;
  const order = ["deterministic", "workflow", "rag", "agent"] as const;
  const color: Record<string, string> = { deterministic: "bg-pass", workflow: "bg-signal", rag: "bg-tool", agent: "bg-llm" };
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full bg-panel-2" role="img" aria-label="Share of catalog entries by recommended approach">
        {order.map((k) => <div key={k} className={color[k]} style={{ width: `${((v[k] ?? 0) / total) * 100}%` }} />)}
      </div>
      <dl className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {order.map((k) => (
          <div key={k}>
            <dt className="flex items-center gap-2 text-sm font-medium">
              <span className={cn("size-2.5 rounded-sm", color[k])} /> {VERDICT_LABEL[k]}
              <span className="ml-auto font-mono text-muted tabular-nums">{v[k] ?? "–"}</span>
            </dt>
            <dd className="mt-1 text-sm text-muted">{VERDICT_HELP[k]}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function DailyAndProjects() {
  const daily = useQuery({ queryKey: ["daily"], queryFn: () => api.get<ExerciseCard & { date: string }>("/challenges/daily") });
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => api.get<{ items: { slug: string; title: string; summary: string; difficulty: string; estimated_hours: number; skills: string[] }[] }>("/projects") });
  return (
    <div className="grid gap-10 lg:grid-cols-[1fr_1.4fr]">
      <div>
        <h3 className="font-display text-xl font-semibold">Today’s challenge</h3>
        <p className="mt-1 text-sm text-muted">Everyone gets the same one. Code runs in an isolated sandbox against hidden tests; points come once, and hints cost a little.</p>
        {daily.data && (
          <Link to={`/challenges/${daily.data.slug}`} className="mt-4 block rounded-lg border border-line bg-panel p-4 hover:border-line-strong">
            <div className="flex items-center gap-2 text-xs text-muted">
              <span>{CATEGORY_LABEL[daily.data.category] ?? daily.data.category}</span>
              <span className="ml-auto">{daily.data.points} points</span>
            </div>
            <p className="mt-1.5 font-medium">{daily.data.title}</p>
            <div className="mt-3"><LevelPips level={daily.data.difficulty} /></div>
          </Link>
        )}
      </div>
      <div>
        <h3 className="font-display text-xl font-semibold">Projects worth putting in a portfolio</h3>
        <ul className="mt-4 divide-y divide-line border-y border-line">
          {projects.data?.items.slice(0, 4).map((p) => (
            <li key={p.slug} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-3">
              <Link to="/projects" className="font-medium hover:text-signal">{p.title}</Link>
              <span className="text-xs text-muted">{p.estimated_hours} h</span>
              <span className="w-full text-sm text-muted">{p.skills.join(", ")}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Badges() {
  const q = useQuery({ queryKey: ["achievements"], queryFn: () => api.get<{ items: { slug: string; name: string; description: string }[] }>("/achievements") });
  return (
    <ul className="mt-8 grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
      {q.data?.items.slice(0, 8).map((a) => (
        <li key={a.slug} className="border-l-2 border-pass/50 pl-3">
          <p className="font-medium">{a.name}</p>
          <p className="text-sm text-muted">{a.description}</p>
        </li>
      ))}
    </ul>
  );
}

function PricingStrip() {
  const q = useQuery({ queryKey: ["plans"], queryFn: () => api.get<{ items: { key: string; name: string; price_hint: string; tagline: string; highlights: string[] }[] }>("/plans") });
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {q.data?.items.map((p) => (
        <div key={p.key} className={cn("rounded-lg border p-5", p.key === "pro" ? "border-signal/60 bg-signal/5" : "border-line")}>
          <div className="flex items-baseline justify-between">
            <span className="font-display text-lg font-semibold">{p.name}</span>
            <span className="text-sm text-muted">{p.price_hint}</span>
          </div>
          <p className="mt-1 text-sm text-muted">{p.tagline}</p>
          <ul className="mt-4 space-y-1.5 text-sm">
            {p.highlights.map((h) => <li key={h} className="flex gap-2"><Check className="mt-0.5 size-4 shrink-0 text-pass" />{h}</li>)}
          </ul>
        </div>
      ))}
    </div>
  );
}

export default function Landing() {
  const nav = useNavigate();
  const { user } = useAuth();
  const palette = useCommandPalette();
  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-30 border-b border-line/70 bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4 sm:px-6">
          <Logo />
          <nav aria-label="Primary" className="hidden gap-5 text-sm text-muted md:flex">
            <Link to="/paths" className="hover:text-fg">Learning paths</Link>
            <Link to="/agents" className="hover:text-fg">Agent library</Link>
            <Link to="/challenges" className="hover:text-fg">Challenges</Link>
            <Link to="/pricing" className="hover:text-fg">Pricing</Link>
          </nav>
          <div className="ml-auto"><TopBarActions onSearch={() => palette.setOpen(true)} /></div>
        </div>
      </header>

      <main id="main">
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-14 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:pt-20">
          <div>
            <h1 className="max-w-[16ch] text-[44px] font-bold leading-[1.02] tracking-[-0.03em] sm:text-[58px] lg:text-[64px]">
              Learn to Build AI Systems That Actually Work.
            </h1>
            <p className="mt-6 max-w-[52ch] text-lg text-muted">
              From your first API to production-grade AI agents. Learn, code, evaluate, deploy, and master real-world engineering.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" onClick={() => nav(user ? "/dashboard" : "/register")}>Start Learning</Button>
              <Button size="lg" variant="secondary" onClick={() => nav("/agents")}>Explore 100+ AI Agents</Button>
              <Button size="lg" variant="ghost" onClick={() => nav("/lab")}>Try the Interactive Lab</Button>
            </div>
            <dl className="mt-10 grid max-w-md grid-cols-3 gap-6 border-t border-line pt-6 text-sm">
              <div><dt className="text-muted">Tracks</dt><dd className="font-display text-2xl font-semibold">16</dd></div>
              <div><dt className="text-muted">Agent blueprints</dt><dd className="font-display text-2xl font-semibold">100</dd></div>
              <div><dt className="text-muted">Runnable agents</dt><dd className="font-display text-2xl font-semibold">10</dd></div>
            </dl>
          </div>
          <HeroRun />
        </section>

        <section className="border-t border-line bg-sunken/60">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <h2 className="text-3xl font-semibold">One roadmap, from fundamentals to production AI</h2>
            <p className="mt-2 max-w-2xl text-muted">
              Every lesson has the same fifteen parts: the idea, why it matters, a mental model, runnable code with expected output,
              common mistakes, debugging, security, interview questions and two challenges.
            </p>
            <div className="mt-10"><Roadmap /></div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 className="text-3xl font-semibold">Most problems don’t need an autonomous agent</h2>
          <p className="mt-2 max-w-2xl text-muted">
            Each of the 100 entries in the library comes with an honest verdict. Here is how they split - and why that matters for cost,
            reliability and safety.
          </p>
          <div className="mt-8"><VerdictSplit /></div>
          <Button variant="link" className="mt-6" onClick={() => nav("/agents")}>Browse the library</Button>
        </section>

        <section className="border-t border-line">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6"><DailyAndProjects /></div>
        </section>

        <section className="border-t border-line bg-sunken/60">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <h2 className="text-3xl font-semibold">Badges you can only earn by doing the work</h2>
            <p className="mt-2 max-w-2xl text-muted">
              Achievements are granted by server-side rules over verifiable records - a passed quiz, a challenge that passed hidden tests,
              a reviewed design. Nothing is awarded for clicking through.
            </p>
            <Badges />
            <h2 className="mt-14 text-3xl font-semibold">Plans</h2>
            <p className="mb-8 mt-2 text-muted">Start free. Paid plans are configurable; no payment provider is wired in yet.</p>
            <PricingStrip />
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-8 text-sm text-muted sm:px-6">
          <Logo />
          <span className="ml-auto">Built as a modular monolith: FastAPI, PostgreSQL, React and an isolated code sandbox.</span>
        </div>
      </footer>
      <CommandPalette open={palette.open} onOpenChange={palette.setOpen} />
    </div>
  );
}
