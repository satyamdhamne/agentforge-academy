import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, ExternalLink, Pencil, Plus, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { EmptyState, ErrorState, PageHeader } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Markdown } from "@/components/Markdown";
import { Mermaid } from "@/components/Mermaid";
import { Logo } from "@/components/layout/Logo";

export interface Entry { id: string; title: string; summary: string; project: { slug: string; title: string } | null; repo_url: string | null; deployment_url: string | null;
  notes_md: string; skills: string[]; architecture_mermaid: string; screenshot_urls: string[]; tests_md: string; evaluation_md: string;
  review_status: "draft" | "submitted" | "verified" | "changes_requested"; verified: boolean; review_feedback?: string | null; reviewed_at: string | null; updated_at: string }
interface Mine { slug: string; headline: string; is_public: boolean; profile_public: boolean; public_url: string; entries: Entry[] }

const STATUS: Record<Entry["review_status"], { label: string; tone: "outline" | "tool" | "pass" | "fail" }> = {
  draft: { label: "Draft", tone: "outline" }, submitted: { label: "Awaiting review", tone: "tool" }, verified: { label: "Verified", tone: "pass" }, changes_requested: { label: "Changes requested", tone: "fail" },
};

type Form = { title: string; summary: string; project_slug: string; repo_url: string; deployment_url: string; notes_md: string; skills: string; architecture_mermaid: string; screenshot_urls: string; tests_md: string; evaluation_md: string };
const empty: Form = { title: "", summary: "", project_slug: "", repo_url: "", deployment_url: "", notes_md: "", skills: "", architecture_mermaid: "", screenshot_urls: "", tests_md: "", evaluation_md: "" };
const toForm = (e: Entry): Form => ({ title: e.title, summary: e.summary, project_slug: e.project?.slug ?? "", repo_url: e.repo_url ?? "", deployment_url: e.deployment_url ?? "", notes_md: e.notes_md,
  skills: e.skills.join(", "), architecture_mermaid: e.architecture_mermaid, screenshot_urls: e.screenshot_urls.join("\n"), tests_md: e.tests_md, evaluation_md: e.evaluation_md });

function EntryEditor({ initial, onDone, id }: { initial: Form; id?: string; onDone: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState<Form>(initial);
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => api.get<{ items: { slug: string; title: string }[] }>("/projects") });
  const save = useMutation({
    mutationFn: () => {
      const body = { ...f, project_slug: f.project_slug || null, repo_url: f.repo_url.trim() || null, deployment_url: f.deployment_url.trim() || null,
        skills: f.skills.split(",").map((s) => s.trim()).filter(Boolean), screenshot_urls: f.screenshot_urls.split(/\s+/).filter(Boolean) };
      return id ? api.put(`/me/portfolio/entries/${id}`, body) : api.post("/me/portfolio/entries", body);
    },
    onSuccess: () => { toast.success("Saved"); qc.invalidateQueries({ queryKey: ["my-portfolio"] }); onDone(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const field = (k: keyof Form, label: string, opts: { rows?: number; placeholder?: string; hint?: string } = {}) => (
    <div>
      <Label htmlFor={`pf-${k}`}>{label}</Label>
      {opts.rows ? <Textarea id={`pf-${k}`} rows={opts.rows} value={f[k]} placeholder={opts.placeholder} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
        : <Input id={`pf-${k}`} value={f[k]} placeholder={opts.placeholder} onChange={(e) => setF({ ...f, [k]: e.target.value })} />}
      {opts.hint && <p className="mt-1 text-xs text-faint">{opts.hint}</p>}
    </div>
  );
  return (
    <form className="space-y-4 rounded-lg border border-line p-5" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div className="grid gap-4 md:grid-cols-2">
        {field("title", "Title")}
        <div><Label htmlFor="pf-project">Based on a platform project (optional)</Label>
          <Select id="pf-project" value={f.project_slug} onChange={(e) => setF({ ...f, project_slug: e.target.value })}>
            <option value="">Independent project</option>{projects.data?.items.map((p) => <option key={p.slug} value={p.slug}>{p.title}</option>)}</Select></div>
      </div>
      {field("summary", "One-line summary", { placeholder: "What it does and who it's for" })}
      <div className="grid gap-4 md:grid-cols-2">
        {field("repo_url", "Repository URL", { placeholder: "https://github.com/you/project", hint: "Required for verification." })}
        {field("deployment_url", "Live demo URL (optional)", { placeholder: "https://" })}
      </div>
      {field("skills", "Skills (comma separated)", { placeholder: "FastAPI, PostgreSQL, RAG, Docker" })}
      {field("notes_md", "What you built and the decisions you made (Markdown)", { rows: 6 })}
      {field("tests_md", "How you tested it", { rows: 3, placeholder: "Test suite, coverage, load tests, evaluation sets" })}
      {field("evaluation_md", "Evaluation results (optional, for AI projects)", { rows: 3, placeholder: "Recall@k, pass rates, before/after numbers" })}
      {field("architecture_mermaid", "Architecture diagram (Mermaid, optional)", { rows: 4, placeholder: "flowchart LR\n  A[Client] --> B[API] --> C[(Postgres)]" })}
      {f.architecture_mermaid.trim() && <div className="rounded-md border border-line p-3"><Mermaid chart={f.architecture_mermaid} /></div>}
      {field("screenshot_urls", "Screenshot URLs (https, one per line, optional)", { rows: 2 })}
      <div className="flex gap-2"><Button type="submit" disabled={save.isPending || f.title.trim().length < 2}>{id ? "Save changes" : "Add entry"}</Button><Button type="button" variant="ghost" onClick={onDone}>Cancel</Button></div>
      {id && <p className="text-xs text-faint">Editing a verified entry returns it to draft until it's verified again.</p>}
    </form>
  );
}

export function EntryView({ e, actions }: { e: Entry; actions?: React.ReactNode }) {
  return (
    <article className="space-y-3 rounded-lg border border-line p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-display text-lg font-semibold">{e.title}</h3>
        {e.verified ? <Badge tone="pass"><BadgeCheck className="size-3.5" />Verified</Badge> : actions && <Badge tone={STATUS[e.review_status].tone}>{STATUS[e.review_status].label}</Badge>}
        {e.project && <Link to="/projects" className="text-xs text-muted hover:text-fg">{e.project.title}</Link>}
        <div className="ml-auto flex gap-1">{actions}</div>
      </div>
      {e.summary && <p className="text-muted">{e.summary}</p>}
      <div className="flex flex-wrap gap-3 text-sm">
        {e.repo_url && <a href={e.repo_url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 text-signal hover:underline">Repository<ExternalLink className="size-3.5" /></a>}
        {e.deployment_url && <a href={e.deployment_url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 text-signal hover:underline">Live demo<ExternalLink className="size-3.5" /></a>}
      </div>
      {e.skills.length > 0 && <div className="flex flex-wrap gap-1.5">{e.skills.map((s) => <Badge key={s} tone="neutral">{s}</Badge>)}</div>}
      {e.notes_md && <Markdown>{e.notes_md}</Markdown>}
      {e.architecture_mermaid && <div className="rounded-md border border-line p-3"><Mermaid chart={e.architecture_mermaid} /></div>}
      {e.tests_md && <div><p className="text-sm font-medium">Testing</p><Markdown className="text-sm">{e.tests_md}</Markdown></div>}
      {e.evaluation_md && <div><p className="text-sm font-medium">Evaluation</p><Markdown className="text-sm">{e.evaluation_md}</Markdown></div>}
      {e.screenshot_urls.length > 0 && <ul className="text-sm">{e.screenshot_urls.map((u) => <li key={u}><a className="text-signal hover:underline" href={u} target="_blank" rel="noopener noreferrer nofollow">Screenshot</a></li>)}</ul>}
    </article>
  );
}

export default function PortfolioPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["my-portfolio"], queryFn: () => api.get<Mine>("/me/portfolio") });
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [headline, setHeadline] = useState<string | null>(null);
  const settings = useMutation({
    mutationFn: (b: { headline: string; is_public: boolean }) => api.patch<Mine>("/me/portfolio", b),
    onSuccess: (d) => { qc.setQueryData(["my-portfolio"], d); setHeadline(null); toast.success(d.is_public ? "Your portfolio is public" : "Saved"); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const submit = useMutation({ mutationFn: (id: string) => api.post(`/me/portfolio/entries/${id}/submit`), onSuccess: () => { toast.success("Sent for review"); qc.invalidateQueries({ queryKey: ["my-portfolio"] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const del = useMutation({ mutationFn: (id: string) => api.delete(`/me/portfolio/entries/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["my-portfolio"] }), onError: (e) => toast.error(errorMessage(e)) });
  if (q.error) return <ErrorState error={q.error} />;
  if (!q.data) return <PageSkeleton />;
  const p = q.data;
  const h = headline ?? p.headline;
  return (
    <div className="space-y-8">
      <PageHeader title="Portfolio" description="Show what you've built with evidence: code, tests, evaluation numbers and architecture. Reviewers verify entries so employers can trust them."
        actions={p.is_public ? <Button asChild variant="secondary"><Link to={p.public_url} target="_blank">View public page<ExternalLink /></Link></Button> : undefined} />
      <section className="flex flex-wrap items-end gap-3 rounded-lg border border-line p-4">
        <div className="min-w-64 flex-1"><Label htmlFor="headline">Headline</Label><Input id="headline" value={h} onChange={(e) => setHeadline(e.target.value)} placeholder="Backend engineer building reliable AI systems" /></div>
        <Button variant="secondary" onClick={() => settings.mutate({ headline: h, is_public: p.is_public })} disabled={settings.isPending || headline === null}>Save headline</Button>
        <label className="flex h-9 items-center gap-2 text-sm"><input type="checkbox" className="accent-[var(--signal)]" checked={p.is_public} onChange={(e) => settings.mutate({ headline: h, is_public: e.target.checked })} />Public</label>
        <p className="w-full text-xs text-faint">{p.is_public ? `Anyone with the link can see submitted and verified entries at ${window.location.origin}${p.public_url}. Drafts stay private.` : "Private. Only you can see it."}</p>
      </section>
      {editing === "new" ? <EntryEditor initial={empty} onDone={() => setEditing(null)} /> : <Button onClick={() => setEditing("new")}><Plus />Add an entry</Button>}
      {p.entries.length === 0 && editing !== "new" ? <EmptyState title="No entries yet">Add a project from the <Link to="/projects" className="text-signal hover:underline">Projects</Link> catalogue or something you built yourself.</EmptyState> : (
        <div className="space-y-4">
          {p.entries.map((e) => editing === e.id ? <EntryEditor key={e.id} id={e.id} initial={toForm(e)} onDone={() => setEditing(null)} /> : (
            <div key={e.id} className="space-y-2">
              <EntryView e={e} actions={<>
                {["draft", "changes_requested"].includes(e.review_status) && <Button size="sm" variant="secondary" onClick={() => submit.mutate(e.id)} disabled={submit.isPending}><Send />Request verification</Button>}
                <Button size="sm" variant="ghost" aria-label={`Edit ${e.title}`} onClick={() => setEditing(e.id)}><Pencil /></Button>
                <Button size="sm" variant="ghost" aria-label={`Delete ${e.title}`} onClick={() => { if (window.confirm(`Delete "${e.title}"?`)) del.mutate(e.id); }}><Trash2 /></Button>
              </>} />
              {e.review_feedback && <p className="rounded-md border border-line bg-panel px-3 py-2 text-sm"><span className="font-medium">Reviewer feedback{e.reviewed_at ? ` (${formatDate(e.reviewed_at)})` : ""}:</span> {e.review_feedback}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface Public { slug: string; name: string; headline: string; bio: string; entries: Entry[]; badges: { name: string; description: string; awarded_at: string }[]; lessons_completed: number }

export function PublicPortfolio() {
  const { slug } = useParams();
  const q = useQuery({ queryKey: ["public-portfolio", slug], queryFn: () => api.get<Public>(`/portfolios/${slug}`) });
  return (
    <div className="min-h-dvh bg-bg">
      <header className="border-b border-line"><div className="mx-auto flex h-14 max-w-4xl items-center px-4"><Logo to="/" /></div></header>
      <main className="mx-auto max-w-4xl px-4 py-10">
        {q.isLoading ? <PageSkeleton /> : q.error || !q.data ? <ErrorState error={q.error ?? new Error("Portfolio not found")} /> : (
          <div className="space-y-10">
            <div>
              <h1 className="text-4xl font-semibold">{q.data.name}</h1>
              {q.data.headline && <p className="mt-2 text-lg text-muted">{q.data.headline}</p>}
              {q.data.bio && <p className="mt-4 max-w-2xl">{q.data.bio}</p>}
              <p className="mt-4 text-sm text-muted">{q.data.lessons_completed} lessons completed on AgentForge Academy</p>
            </div>
            {q.data.badges.length > 0 && (
              <section><h2 className="mb-3 font-display text-lg font-semibold">Achievements</h2>
                <ul className="flex flex-wrap gap-2">{q.data.badges.map((b) => <li key={b.name} title={b.description}><Badge tone="signal">{b.name}</Badge></li>)}</ul></section>
            )}
            <section className="space-y-4">
              <h2 className="font-display text-lg font-semibold">Projects</h2>
              {q.data.entries.length ? q.data.entries.map((e) => <EntryView key={e.id} e={e} />) : <p className="text-muted">No projects shared yet.</p>}
              <p className="text-xs text-faint">Entries marked Verified were reviewed by an AgentForge reviewer against the repository and evidence provided.</p>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
