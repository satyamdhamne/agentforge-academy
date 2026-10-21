import { useState } from "react";
import { NavLink, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, formatDate, titleCase } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { CodeEditor } from "@/components/LazyEditor";
import { Markdown } from "@/components/Markdown";
import { ErrorState, EmptyState } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";

/* ---------------------------------------------------------------- analytics */

interface Analytics {
  kpis: Record<string, number | null>;
  series: Record<string, number | string>[];
  runs_by_provider_30d: Record<string, number>;
  pending_reviews: number;
  privacy_note: string;
}

const KPI_LABELS: [string, string, (v: number | null) => string][] = [
  ["users_total", "Learners", (v) => String(v ?? 0)],
  ["activation_rate", "Activation (completed a lesson)", (v) => `${Math.round((v ?? 0) * 100)}%`],
  ["weekly_active_learners", "Weekly active learners", (v) => String(v ?? 0)],
  ["week1_retention", "Week-1 retention", (v) => (v === null ? "Not enough data" : `${Math.round(v * 100)}%`)],
  ["lesson_completions_7d", "Lesson completions, 7 days", (v) => String(v ?? 0)],
  ["challenge_completions_7d", "Challenges passed, 7 days", (v) => String(v ?? 0)],
  ["agent_demo_users_7d", "Learners running agents, 7 days", (v) => String(v ?? 0)],
  ["projects_verified", "Verified projects", (v) => String(v ?? 0)],
  ["paid_conversion", "Paid conversion", (v) => `${Math.round((v ?? 0) * 1000) / 10}%`],
  ["inference_cost_usd_30d", "Inference cost, 30 days", (v) => `$${(v ?? 0).toFixed(2)}`],
];

function Overview() {
  const q = useQuery({ queryKey: ["admin-analytics"], queryFn: () => api.get<Analytics>("/admin/analytics") });
  if (q.isLoading) return <PageSkeleton />;
  if (q.error) return q.error instanceof ApiError && q.error.status === 403 ? <p className="text-muted">Analytics are available to admins.</p> : <ErrorState error={q.error} />;
  const d = q.data!;
  return (
    <div className="space-y-10">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-6 sm:grid-cols-3 lg:grid-cols-5">
        {KPI_LABELS.map(([k, label, f]) => <div key={k}><dt className="text-xs text-muted">{label}</dt><dd className="font-display text-2xl font-semibold tabular-nums">{f(d.kpis[k] ?? null)}</dd></div>)}
      </dl>
      {d.kpis.runs_without_price_30d ? <p className="text-sm text-tool">{d.kpis.runs_without_price_30d} runs in the last 30 days used a model without a configured price, so cost is understated. Set MODEL_PRICES.</p> : null}
      <div>
        <h2 className="mb-3 font-display text-lg font-semibold">Last 14 days</h2>
        <div className="h-72 rounded-lg border border-line p-3">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={d.series.map((r) => ({ lesson_completed: 0, challenge_attempted: 0, agent_run: 0, user_registered: 0, ...r }))}>
              <CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="date" tickFormatter={(v: string) => v.slice(5)} tick={{ fill: "var(--fg-faint)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fill: "var(--fg-faint)", fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 6, fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area type="monotone" dataKey="lesson_completed" name="Lessons completed" stroke="var(--pass)" fill="var(--pass)" fillOpacity={0.12} />
              <Area type="monotone" dataKey="challenge_attempted" name="Challenge attempts" stroke="var(--signal)" fill="var(--signal)" fillOpacity={0.12} />
              <Area type="monotone" dataKey="agent_run" name="Agent runs" stroke="var(--llm)" fill="var(--llm)" fillOpacity={0.12} />
              <Area type="monotone" dataKey="user_registered" name="Sign-ups" stroke="var(--tool)" fill="var(--tool)" fillOpacity={0.12} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
      <p className="text-xs text-faint">{d.privacy_note}</p>
    </div>
  );
}

/* ---------------------------------------------------------------- lessons CMS */

interface AdminLesson { id: string; slug: string; title: string; status: string; tier: string; track: string; published_version: number | null; pending_review: number; updated_at: string }
interface Version { id: string; version: number; status: string; change_note: string; created_at: string; published_at: string | null }

function LessonsList() {
  const nav = useNavigate();
  const [status, setStatus] = useState("");
  const q = useQuery({ queryKey: ["admin-lessons", status], queryFn: () => api.get<{ items: AdminLesson[]; total: number }>("/admin/lessons", { params: { status, page_size: 200 } }) });
  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <Select aria-label="Status" className="w-48" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option><option value="published">Published</option><option value="draft">Draft (outline only)</option>
        </Select>
        <span className="text-sm text-muted">{q.data?.total ?? ""} lessons</span>
      </div>
      {q.error && <ErrorState error={q.error} />}
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel-2 text-left text-muted"><tr><th className="px-3 py-2 font-medium">Lesson</th><th className="px-3 py-2 font-medium">Track</th><th className="px-3 py-2 font-medium">Status</th><th className="px-3 py-2 font-medium">Live version</th><th className="px-3 py-2 font-medium">In review</th></tr></thead>
          <tbody>
            {q.data?.items.map((l) => (
              <tr key={l.id} className="cursor-pointer border-t border-line hover:bg-panel-2/50" onClick={() => nav(`/admin/lessons/${l.id}`)}>
                <td className="px-3 py-2"><span className="font-medium">{l.title}</span><span className="block font-mono text-xs text-faint">{l.slug}</span></td>
                <td className="px-3 py-2 text-muted">{l.track}</td>
                <td className="px-3 py-2"><Badge tone={l.status === "published" ? "pass" : "neutral"}>{titleCase(l.status)}</Badge></td>
                <td className="px-3 py-2 tabular-nums">{l.published_version ? `v${l.published_version}` : "-"}</td>
                <td className="px-3 py-2">{l.pending_review ? <Badge tone="tool">{l.pending_review}</Badge> : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LessonEditor() {
  const { id = "" } = useParams();
  const { isReviewer, user } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-lesson", id], queryFn: () => api.get<{ id: string; slug: string; title: string; status: string; versions: Version[]; latest_content: unknown; required_sections: string[] }>(`/admin/lessons/${id}`) });
  const [json, setJson] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [problems, setProblems] = useState<string[]>([]);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["admin-lesson", id] }); qc.invalidateQueries({ queryKey: ["admin-lessons"] }); };
  const create = useMutation({
    mutationFn: (content: unknown) => api.post<Version>(`/admin/lessons/${id}/versions`, { content, change_note: note }),
    onSuccess: (v) => { toast.success(`Saved draft v${v.version}`); setNote(""); setProblems([]); refresh(); },
    onError: (e) => { if (e instanceof ApiError && Array.isArray(e.details)) setProblems(e.details.map(String)); toast.error(errorMessage(e)); },
  });
  const act = useMutation({
    mutationFn: ({ vid, action }: { vid: string; action: "submit" | "publish" | "reject" }) => api.post<Version>(`/admin/lesson-versions/${vid}/${action}`),
    onSuccess: (v) => { toast.success(`Version ${v.version} is now ${v.status}`); refresh(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (q.isLoading) return <PageSkeleton />;
  if (q.error) return <ErrorState error={q.error} />;
  const d = q.data!;
  const text = json ?? JSON.stringify(d.latest_content ?? { sections: Object.fromEntries(d.required_sections.map((s) => [s, ""])) }, null, 2);
  const save = () => {
    try { create.mutate(JSON.parse(text)); } catch (e) { toast.error(`Content isn’t valid JSON: ${(e as Error).message}`); }
  };
  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="min-w-0 space-y-4">
        <div>
          <h2 className="font-display text-xl font-semibold">{d.title}</h2>
          <p className="font-mono text-xs text-faint">{d.slug}</p>
        </div>
        <p className="text-sm text-muted">Edit the structured lesson content. Saving creates a new draft version; the live lesson changes only when a reviewer publishes it. Required sections: {d.required_sections.join(", ")}.</p>
        <CodeEditor value={text} onChange={setJson} language="json" height={560} ariaLabel="Lesson content JSON" />
        {problems.length > 0 && <p className="text-sm text-fail">Missing sections: {problems.join(", ")}</p>}
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-64 flex-1"><Label htmlFor="note">Change note</Label><Input id="note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="What changed and why" /></div>
          <Button onClick={save} disabled={note.trim().length < 3 || create.isPending}>Save as draft</Button>
        </div>
      </div>
      <aside>
        <h3 className="mb-2 text-sm font-medium">Version history</h3>
        <ol className="space-y-2">
          {d.versions.map((v) => (
            <li key={v.id} className="rounded-lg border border-line p-3 text-sm">
              <div className="flex items-center gap-2"><span className="font-mono">v{v.version}</span><Badge tone={v.status === "published" ? "pass" : v.status === "review" ? "tool" : "neutral"}>{titleCase(v.status)}</Badge></div>
              <p className="mt-1 text-muted">{v.change_note}</p>
              <p className="mt-1 text-xs text-faint">{formatDate(v.created_at)}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {v.status === "draft" && <Button size="sm" variant="secondary" onClick={() => act.mutate({ vid: v.id, action: "submit" })}>Submit for review</Button>}
                {v.status === "review" && isReviewer && <>
                  <Button size="sm" onClick={() => act.mutate({ vid: v.id, action: "publish" })}>Publish</Button>
                  <Button size="sm" variant="ghost" onClick={() => act.mutate({ vid: v.id, action: "reject" })}>Send back</Button>
                </>}
              </div>
            </li>
          ))}
        </ol>
        {!user?.roles.includes("admin") && <p className="mt-3 text-xs text-faint">Authors can’t publish their own changes; a different reviewer must approve.</p>}
      </aside>
    </div>
  );
}

/* ---------------------------------------------------------------- review queue */

interface ReviewItem { id: string; exercise: { slug: string; title: string; points: number; rubric: { criterion: string; weight?: number; description: string }[]; prompt_md: string }; answer_text: string; submitted_at: string }

function ReviewCard({ item }: { item: ReviewItem }) {
  const qc = useQueryClient();
  const [scores, setScores] = useState<Record<string, number>>(() => Object.fromEntries(item.exercise.rubric.map((r) => [r.criterion, 0.5])));
  const [feedback, setFeedback] = useState("");
  const m = useMutation({
    mutationFn: () => api.post<{ score: number; points_awarded: number }>(`/admin/attempts/${item.id}/review`, { scores, feedback }),
    onSuccess: (r) => { toast.success(`Reviewed: ${Math.round(r.score * 100)}%, ${r.points_awarded} points awarded`); qc.invalidateQueries({ queryKey: ["reviews"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <article className="grid gap-6 rounded-lg border border-line p-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <div className="min-w-0">
        <p className="text-xs text-muted">Submitted {formatDate(item.submitted_at)}</p>
        <h3 className="font-display text-lg font-semibold">{item.exercise.title}</h3>
        <details className="mt-1"><summary className="cursor-pointer text-sm text-muted">Challenge brief</summary><Markdown className="mt-2 text-sm">{item.exercise.prompt_md}</Markdown></details>
        <div className="mt-4 max-h-[480px] overflow-auto rounded-md border border-line bg-sunken p-4 scrollbar-thin"><Markdown>{item.answer_text}</Markdown></div>
      </div>
      <div className="space-y-4">
        {item.exercise.rubric.map((r) => (
          <div key={r.criterion}>
            <div className="flex items-baseline justify-between"><Label htmlFor={`${item.id}-${r.criterion}`} className="mb-0">{titleCase(r.criterion)}</Label><span className="font-mono text-sm tabular-nums">{Math.round(scores[r.criterion] * 100)}%</span></div>
            <p className="mb-1 text-xs text-muted">{r.description}{r.weight ? ` Weight ${r.weight}.` : ""}</p>
            <input id={`${item.id}-${r.criterion}`} type="range" min={0} max={1} step={0.05} value={scores[r.criterion]} onChange={(e) => setScores({ ...scores, [r.criterion]: Number(e.target.value) })} className="w-full accent-[var(--signal)]" />
          </div>
        ))}
        <div><Label htmlFor={`${item.id}-fb`}>Feedback for the learner</Label><Textarea id={`${item.id}-fb`} rows={4} value={feedback} onChange={(e) => setFeedback(e.target.value)} /></div>
        <Button onClick={() => m.mutate()} disabled={feedback.trim().length < 10 || m.isPending}>Submit review</Button>
      </div>
    </article>
  );
}

function Reviews() {
  const q = useQuery({ queryKey: ["reviews"], queryFn: () => api.get<{ items: ReviewItem[] }>("/admin/reviews") });
  if (q.isLoading) return <PageSkeleton />;
  if (q.error) return q.error instanceof ApiError && q.error.status === 403 ? <p className="text-muted">The review queue is for reviewers.</p> : <ErrorState error={q.error} />;
  if (!q.data!.items.length) return <EmptyState title="Nothing waiting for review">Architecture answers, prompt rewrites and weekly projects appear here when learners submit them.</EmptyState>;
  return <div className="space-y-6">{q.data!.items.map((i) => <ReviewCard key={i.id} item={i} />)}</div>;
}

/* ---------------------------------------------------------------- users, audit, announcements */

function Users() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const q = useQuery({ queryKey: ["admin-users", search], queryFn: () => api.get<{ items: { id: string; email: string; display_name: string; roles: string[]; plan: string; verified: boolean; created_at: string }[]; total: number }>("/admin/users", { params: { q: search } }) });
  const plan = useMutation({
    mutationFn: ({ id, p }: { id: string; p: string }) => api.patch(`/admin/users/${id}/plan`, { plan: p }),
    onSuccess: () => { toast.success("Plan updated and audit-logged"); qc.invalidateQueries({ queryKey: ["admin-users"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (q.error) return q.error instanceof ApiError && q.error.status === 403 ? <p className="text-muted">User management is for admins.</p> : <ErrorState error={q.error} />;
  return (
    <div>
      <Input aria-label="Search by email" placeholder="Search by email" className="mb-4 max-w-xs" value={search} onChange={(e) => setSearch(e.target.value)} />
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel-2 text-left text-muted"><tr><th className="px-3 py-2 font-medium">Learner</th><th className="px-3 py-2 font-medium">Roles</th><th className="px-3 py-2 font-medium">Joined</th><th className="px-3 py-2 font-medium">Plan</th></tr></thead>
          <tbody>
            {q.data?.items.map((u) => (
              <tr key={u.id} className="border-t border-line">
                <td className="px-3 py-2"><span className="font-medium">{u.display_name}</span><span className="block text-xs text-muted">{u.email}{u.verified ? "" : ", unverified"}</span></td>
                <td className="px-3 py-2 text-muted">{u.roles.join(", ")}</td>
                <td className="px-3 py-2 text-muted">{formatDate(u.created_at)}</td>
                <td className="px-3 py-2">
                  <Select aria-label={`Plan for ${u.email}`} className="h-8 w-28" value={u.plan} onChange={(e) => plan.mutate({ id: u.id, p: e.target.value })}>
                    <option value="free">Free</option><option value="pro">Pro</option><option value="team">Team</option>
                  </Select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Audit() {
  const q = useQuery({ queryKey: ["audit"], queryFn: () => api.get<{ items: { id: string; action: string; entity_type: string; entity_id: string | null; before: unknown; after: unknown; trace_id: string | null; created_at: string }[] }>("/admin/audit-logs") });
  if (q.error) return q.error instanceof ApiError && q.error.status === 403 ? <p className="text-muted">The audit log is for admins.</p> : <ErrorState error={q.error} />;
  return (
    <ul className="divide-y divide-line rounded-lg border border-line text-sm">
      {q.data?.items.map((x) => (
        <li key={x.id} className="grid gap-1 px-4 py-2.5 sm:grid-cols-[11rem_14rem_1fr]">
          <span className="text-muted">{new Date(x.created_at).toLocaleString()}</span>
          <span className="font-mono text-xs">{x.action}</span>
          <span className="truncate font-mono text-xs text-muted">{x.entity_type}:{x.entity_id} {x.after ? JSON.stringify(x.after) : ""}</span>
        </li>
      ))}
    </ul>
  );
}

function Announcements() {
  const [form, setForm] = useState({ title: "", body_md: "", publish: true });
  const m = useMutation({ mutationFn: () => api.post("/admin/announcements", form), onSuccess: () => { toast.success(form.publish ? "Announcement published" : "Draft saved"); setForm({ title: "", body_md: "", publish: true }); }, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <form className="max-w-xl space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
      <div><Label htmlFor="at">Title</Label><Input id="at" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></div>
      <div><Label htmlFor="ab">Message (Markdown)</Label><Textarea id="ab" rows={5} value={form.body_md} onChange={(e) => setForm({ ...form, body_md: e.target.value })} /></div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-[var(--signal)]" checked={form.publish} onChange={(e) => setForm({ ...form, publish: e.target.checked })} />Publish now</label>
      <Button type="submit" disabled={form.title.length < 3 || form.body_md.length < 3 || m.isPending}>{form.publish ? "Publish announcement" : "Save draft"}</Button>
    </form>
  );
}

interface PortfolioReview { id: string; title: string; summary: string; learner: string; repo_url: string | null; deployment_url: string | null; notes_md: string; tests_md: string; evaluation_md: string; skills: string[]; updated_at: string }

function PortfolioReviewCard({ e }: { e: PortfolioReview }) {
  const qc = useQueryClient();
  const [feedback, setFeedback] = useState("");
  const decide = useMutation({
    mutationFn: (decision: "verify" | "request_changes") => api.post(`/admin/portfolio-entries/${e.id}/review`, { decision, feedback }),
    onSuccess: (_, d) => { toast.success(d === "verify" ? "Verified" : "Sent back with feedback"); qc.invalidateQueries({ queryKey: ["admin-portfolio-reviews"] }); },
    onError: (err) => toast.error(errorMessage(err)),
  });
  return (
    <li className="space-y-3 rounded-lg border border-line p-5">
      <div className="flex flex-wrap items-baseline gap-2"><p className="font-display text-lg font-semibold">{e.title}</p><span className="text-sm text-muted">by {e.learner}</span>
        <span className="ml-auto text-xs text-muted">{formatDate(e.updated_at)}</span></div>
      {e.summary && <p className="text-muted">{e.summary}</p>}
      <div className="flex flex-wrap gap-3 text-sm">
        {e.repo_url && <a className="text-signal hover:underline" href={e.repo_url} target="_blank" rel="noopener noreferrer nofollow">Repository</a>}
        {e.deployment_url && <a className="text-signal hover:underline" href={e.deployment_url} target="_blank" rel="noopener noreferrer nofollow">Live demo</a>}
        {e.skills.length > 0 && <span className="text-muted">{e.skills.join(", ")}</span>}
      </div>
      {e.notes_md && <Markdown className="text-sm">{e.notes_md}</Markdown>}
      {e.tests_md && <div className="text-sm"><p className="font-medium">Testing</p><Markdown>{e.tests_md}</Markdown></div>}
      {e.evaluation_md && <div className="text-sm"><p className="font-medium">Evaluation</p><Markdown>{e.evaluation_md}</Markdown></div>}
      <div><Label htmlFor={`pr-${e.id}`}>Feedback for the learner (at least 10 characters)</Label><Textarea id={`pr-${e.id}`} rows={3} value={feedback} onChange={(ev) => setFeedback(ev.target.value)} /></div>
      <div className="flex gap-2">
        <Button onClick={() => decide.mutate("verify")} disabled={feedback.trim().length < 10 || decide.isPending}>Verify</Button>
        <Button variant="secondary" onClick={() => decide.mutate("request_changes")} disabled={feedback.trim().length < 10 || decide.isPending}>Request changes</Button>
      </div>
      <p className="text-xs text-faint">Check that the repository exists, runs as described and matches the claims before verifying.</p>
    </li>
  );
}

function PortfolioReviews() {
  const q = useQuery({ queryKey: ["admin-portfolio-reviews"], queryFn: () => api.get<{ items: PortfolioReview[] }>("/admin/portfolio-reviews") });
  if (q.error) return <ErrorState error={q.error} />;
  if (!q.data) return <PageSkeleton />;
  return q.data.items.length ? <ul className="space-y-4">{q.data.items.map((e) => <PortfolioReviewCard key={e.id} e={e} />)}</ul>
    : <EmptyState title="No portfolio entries waiting">Learners' verification requests will appear here.</EmptyState>;
}

export default function Admin() {
  const { isAdmin, isReviewer } = useAuth();
  const tabs = [
    { to: "/admin", label: "Overview", end: true, show: isAdmin },
    { to: "/admin/lessons", label: "Lessons", show: true },
    { to: "/admin/reviews", label: "Review queue", show: isReviewer },
    { to: "/admin/portfolio", label: "Portfolio verification", show: isReviewer },
    { to: "/admin/users", label: "Users & plans", show: isAdmin },
    { to: "/admin/audit", label: "Audit log", show: isAdmin },
    { to: "/admin/announcements", label: "Announcements", show: true },
  ].filter((t) => t.show);
  return (
    <div>
      <h1 className="text-3xl font-semibold">Admin CMS</h1>
      <nav className="mb-8 mt-5 flex gap-1 overflow-x-auto border-b border-line" aria-label="Admin sections">
        {tabs.map((t) => (
          <NavLink key={t.to} to={t.to} end={t.end} className={({ isActive }) => cn("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm", isActive ? "border-signal text-fg" : "border-transparent text-muted hover:text-fg")}>{t.label}</NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={isAdmin ? <Overview /> : <LessonsList />} />
        <Route path="lessons" element={<LessonsList />} />
        <Route path="lessons/:id" element={<LessonEditor />} />
        <Route path="reviews" element={<Reviews />} />
        <Route path="portfolio" element={<PortfolioReviews />} />
        <Route path="users" element={<Users />} />
        <Route path="audit" element={<Audit />} />
        <Route path="announcements" element={<Announcements />} />
      </Routes>
    </div>
  );
}
