import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, FlaskConical, Lock, Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, ErrorState, PageHeader } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Metric, metricLabel, ModeBadge, SimulatorNote, pct } from "@/components/LabBits";

interface Opt { key: string; label: string; note?: string; available?: boolean }
interface Options { chunkers: Opt[]; strategies: Opt[]; embedders: Opt[]; defaults: Cfg; default_prompt: { system: string; user: string }; your_groups: string[] }
interface Cfg { chunker: string; size: number; overlap: number; embedder: string }
interface DatasetCard { id: string; slug: string; name: string; description: string; mine: boolean; documents: number; questions: number }
interface Doc { id: string; title: string; source: string; mime: string; allowed_groups: string[]; words: number; readable: boolean; preview: string | null }
interface Dataset { id: string; slug: string; name: string; description: string; mine: boolean; documents: Doc[];
  questions: { question: string; relevant_sources: string[]; user_groups: string[] }[]; indexes: { config: Cfg; chunks: number; backend: string; build_ms: number }[]; your_groups: string[] }
interface Hit { rank: number; chunk_id: string; document: string; source: string; heading: string | null; text: string; tokens: number;
  scores: { vector?: number | null; keyword?: number | null; fused?: number | null; rerank?: number | null }; score: number }
interface QueryOut { retrieved: Hit[]; index: { chunks: number; backend: string; build_ms: number }; stages: { stage: string; ms: number; detail?: string }[];
  latency_ms: number; mode: string | null; provider_label: string | null;
  generation?: { answer: string; error?: string; citations: { n: number; document: string; source: string; heading: string | null; quote: string }[];
    invalid_citations: number[]; grounded: boolean; says_unknown: boolean; input_tokens: number; output_tokens: number; latency_ms: number; cost_usd: number | null; prompt?: string | { system: string; user: string } } }
interface EvalOut { evaluation_id: string; metrics: Record<string, number>; passed: number; total: number; duration_ms: number; message?: string;
  cases: { question: string; groups: string[]; relevant: string[]; retrieved_sources: string[]; recall: number; reciprocal_rank: number; hit: boolean; passed: boolean; answer?: string; answer_ok?: boolean; grounded?: boolean }[] }

const fmtScore = (v?: number | null) => (v === null || v === undefined ? "–" : v.toFixed(3));

function ConfigPanel({ o, cfg, set }: { o: Options; cfg: RunCfg; set: (c: RunCfg) => void }) {
  const chunkNote = o.chunkers.find((c) => c.key === cfg.chunker)?.note;
  const embNote = o.embedders.find((c) => c.key === cfg.embedder)?.note;
  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="chunker">Chunking</Label>
        <Select id="chunker" value={cfg.chunker} onChange={(e) => set({ ...cfg, chunker: e.target.value })}>
          {o.chunkers.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </Select>
        {chunkNote && <p className="mt-1 text-xs text-faint">{chunkNote}</p>}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div><Label htmlFor="size">Size (words)</Label><Input id="size" type="number" min={20} max={1000} value={cfg.size} onChange={(e) => set({ ...cfg, size: Number(e.target.value) })} /></div>
        <div><Label htmlFor="overlap">Overlap</Label><Input id="overlap" type="number" min={0} max={500} value={cfg.overlap} onChange={(e) => set({ ...cfg, overlap: Number(e.target.value) })} /></div>
      </div>
      <div>
        <Label htmlFor="embedder">Embedding model</Label>
        <Select id="embedder" value={cfg.embedder} onChange={(e) => set({ ...cfg, embedder: e.target.value })}>
          {o.embedders.map((c) => <option key={c.key} value={c.key} disabled={!c.available}>{c.label}{c.available ? "" : " (not enabled)"}</option>)}
        </Select>
        {embNote && <p className="mt-1 text-xs text-faint">{embNote}</p>}
      </div>
      <div>
        <Label>Retrieval</Label>
        <div className="flex rounded-md border border-line p-0.5" role="radiogroup" aria-label="Retrieval strategy">
          {o.strategies.map((s) => (
            <button key={s.key} role="radio" aria-checked={cfg.strategy === s.key} onClick={() => set({ ...cfg, strategy: s.key })}
              className={cn("flex-1 rounded px-2 py-1 text-xs", cfg.strategy === s.key ? "bg-panel-2 text-fg" : "text-muted hover:text-fg")}>{s.label}</button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 items-end gap-3">
        <div><Label htmlFor="topk">Top k</Label><Input id="topk" type="number" min={1} max={12} value={cfg.top_k} onChange={(e) => set({ ...cfg, top_k: Number(e.target.value) })} /></div>
        <label className="flex h-9 items-center gap-2 text-sm"><input type="checkbox" className="accent-[var(--signal)]" checked={cfg.rerank} onChange={(e) => set({ ...cfg, rerank: e.target.checked })} />Rerank</label>
      </div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-[var(--signal)]" checked={cfg.generate} onChange={(e) => set({ ...cfg, generate: e.target.checked })} />Generate a grounded answer</label>
      <p className="text-xs text-faint">Your access groups: {o.your_groups.join(", ")}. Documents restricted to other groups are filtered out before retrieval, never after.</p>
    </div>
  );
}

interface RunCfg extends Cfg { strategy: string; top_k: number; rerank: boolean; generate: boolean }

function AskTab({ ds, cfg, prompt }: { ds: Dataset; cfg: RunCfg; prompt: { system: string; user: string } }) {
  const { user } = useAuth();
  const [question, setQuestion] = useState("");
  const run = useMutation({
    mutationFn: (q: string) => api.post<QueryOut>("/rag/query", { dataset: ds.slug, question: q, ...cfg, system_prompt: prompt.system, user_template: prompt.user }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const r = run.data;
  const ask = (q: string) => { setQuestion(q); if (q.trim().length >= 3) run.mutate(q); };
  return (
    <div className="space-y-6">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(question); }}>
        <Input aria-label="Question" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask a question about these documents" />
        <Button type="submit" disabled={!user || run.isPending || question.trim().length < 3}><Search />{run.isPending ? "Searching…" : "Ask"}</Button>
      </form>
      {!user && <p className="text-sm text-muted"><Link to="/login?next=/labs/rag" className="text-signal hover:underline">Sign in</Link> to run queries.</p>}
      {ds.questions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {ds.questions.slice(0, 8).map((q) => (
            <button key={q.question} onClick={() => ask(q.question)} disabled={!user} className="rounded-full border border-line px-2.5 py-0.5 text-left text-xs text-muted hover:text-fg disabled:opacity-60">{q.question}</button>
          ))}
        </div>
      )}
      {r && (
        <div className="space-y-6" aria-live="polite">
          <ol className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted" aria-label="Pipeline stages">
            {r.stages.map((s) => <li key={s.stage} title={s.detail}><span className="text-fg">{s.stage}</span> {s.ms} ms</li>)}
            <li className="ml-auto">Index: {r.index.chunks} chunks in {r.index.backend}</li>
          </ol>
          {r.generation && (
            <section className="space-y-3 rounded-lg border border-line bg-panel p-4">
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                <h3 className="mr-2 font-display text-base font-semibold text-fg">Answer</h3>
                <ModeBadge mode={r.mode} label={r.provider_label} />
                <Badge tone={r.generation.grounded ? "pass" : "fail"}>{r.generation.grounded ? "Grounded" : "Not grounded"}</Badge>
                {r.generation.says_unknown && <Badge tone="outline">Declined: not in sources</Badge>}
                <span>{r.generation.input_tokens} in / {r.generation.output_tokens} out tokens</span>
              </div>
              {r.generation.error ? <p className="text-sm text-fail">{r.generation.error}</p> : <p className="whitespace-pre-wrap">{r.generation.answer}</p>}
              {r.generation.invalid_citations.length > 0 && (
                <p className="text-sm text-fail">Cites passages that weren't retrieved: {r.generation.invalid_citations.map((n) => `[${n}]`).join(" ")}. Treat those claims as unsupported.</p>
              )}
              {r.generation.citations.length > 0 && (
                <ol className="space-y-1 text-sm">
                  {r.generation.citations.map((c) => (
                    <li key={c.n} className="text-muted"><span className="font-mono text-fg">[{c.n}]</span> {c.document}{c.heading ? `, ${c.heading}` : ""}: <span className="italic">"{c.quote}"</span></li>
                  ))}
                </ol>
              )}
              {r.generation.prompt && (
                <details><summary className="cursor-pointer text-xs text-muted">Prompt sent to the model</summary>
                  <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-sunken p-3 font-mono text-xs">{typeof r.generation.prompt === "string" ? r.generation.prompt : `System:\n${r.generation.prompt.system}\n\nUser:\n${r.generation.prompt.user}`}</pre></details>
              )}
            </section>
          )}
          <section>
            <h3 className="mb-2 font-display text-base font-semibold">Retrieved passages</h3>
            {r.retrieved.length === 0 ? <p className="text-sm text-muted">Nothing passed the relevance threshold. A grounded system should say it doesn't know rather than guess.</p> : (
              <ol className="space-y-3">
                {r.retrieved.map((h) => (
                  <li key={h.chunk_id} className="rounded-lg border border-line p-3">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                      <span className="font-mono text-fg">#{h.rank}</span><span className="font-medium text-fg">{h.document}</span>{h.heading && <span>{h.heading}</span>}
                      <span className="ml-auto font-mono">vector {fmtScore(h.scores.vector)}</span><span className="font-mono">bm25 {fmtScore(h.scores.keyword)}</span>
                      {h.scores.fused !== undefined && h.scores.fused !== null && <span className="font-mono">rrf {fmtScore(h.scores.fused)}</span>}
                      {h.scores.rerank !== undefined && h.scores.rerank !== null && <span className="font-mono text-signal">rerank {fmtScore(h.scores.rerank)}</span>}
                    </div>
                    <p className="mt-2 line-clamp-5 whitespace-pre-wrap text-sm">{h.text}</p>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function DocumentsTab({ ds, cfg }: { ds: Dataset; cfg: RunCfg }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [pdf, setPdf] = useState<{ name: string; b64: string } | null>(null);
  const [groups, setGroups] = useState("everyone");
  const preview = useMutation({
    mutationFn: (id: string) => api.post<{ chunks: { n: number; text: string; heading: string | null; words: number }[]; stats: { count: number; avg_words: number } }>(
      `/rag/datasets/${ds.slug}/chunk-preview`, { document_id: id, chunker: cfg.chunker, size: cfg.size, overlap: cfg.overlap }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const add = useMutation({
    mutationFn: () => api.post(`/rag/datasets/${ds.slug}/documents`, { title, filename: pdf?.name ?? `${title}.md`, text: pdf ? null : text, pdf_base64: pdf?.b64 ?? null,
      allowed_groups: groups.split(",").map((g) => g.trim()).filter(Boolean) }),
    onSuccess: () => { toast.success("Document added"); setTitle(""); setText(""); setPdf(null); qc.invalidateQueries({ queryKey: ["rag-dataset", ds.slug] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: (id: string) => api.delete(`/rag/datasets/${ds.slug}/documents/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rag-dataset", ds.slug] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const onFile = (f: File | undefined) => {
    if (!f) return;
    if (f.size > 2_000_000) return toast.error("Files up to 2 MB.");
    const reader = new FileReader();
    if (f.type === "application/pdf" || f.name.endsWith(".pdf")) {
      reader.onload = () => setPdf({ name: f.name, b64: String(reader.result).split(",")[1] ?? "" });
      reader.readAsDataURL(f);
    } else {
      reader.onload = () => { setText(String(reader.result)); setPdf(null); };
      reader.readAsText(f);
    }
    if (!title) setTitle(f.name.replace(/\.[^.]+$/, ""));
  };
  return (
    <div className="space-y-6">
      <ul className="divide-y divide-line rounded-lg border border-line">
        {ds.documents.map((d) => (
          <li key={d.id} className="p-3">
            <div className="flex flex-wrap items-center gap-2">
              <button className="text-left font-medium hover:text-signal disabled:hover:text-fg" disabled={!d.readable} onClick={() => setOpen(open === d.id ? null : d.id)}>{d.title}</button>
              <span className="text-xs text-muted">{d.words} words</span>
              {d.allowed_groups.filter((g) => g !== "everyone").map((g) => <Badge key={g} tone="tool"><Lock className="size-3" />{g}</Badge>)}
              {!d.readable && <span className="text-xs text-muted">Hidden from you: not in your groups</span>}
              <div className="ml-auto flex gap-1">
                {d.readable && <Button size="sm" variant="ghost" onClick={() => { setOpen(d.id); preview.mutate(d.id); }}>Preview chunks</Button>}
                {ds.mine && <Button size="sm" variant="ghost" aria-label={`Delete ${d.title}`} onClick={() => del.mutate(d.id)}><Trash2 /></Button>}
              </div>
            </div>
            {open === d.id && d.preview && (
              <div className="mt-3 space-y-3">
                {preview.data && preview.variables === d.id ? (
                  <div>
                    <p className="mb-2 text-xs text-muted">{preview.data.stats.count} chunks, about {preview.data.stats.avg_words} words each, with {cfg.chunker} {cfg.size}/{cfg.overlap}</p>
                    <ol className="max-h-96 space-y-2 overflow-auto">
                      {preview.data.chunks.map((c) => (
                        <li key={c.n} className="rounded border border-line bg-sunken p-2 text-xs">
                          <span className="font-mono text-faint">{c.n}</span>{c.heading && <span className="ml-2 text-signal">{c.heading}</span>}<span className="ml-2 text-faint">{c.words} words</span>
                          <p className="mt-1 whitespace-pre-wrap">{c.text}</p>
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : <pre className="whitespace-pre-wrap rounded bg-sunken p-3 text-xs text-muted">{d.preview}{d.words > 100 ? "…" : ""}</pre>}
              </div>
            )}
          </li>
        ))}
      </ul>
      {ds.mine ? (
        <section className="space-y-3 rounded-lg border border-line p-4">
          <h3 className="font-display text-base font-semibold">Add a document</h3>
          <div className="grid gap-3 md:grid-cols-2">
            <div><Label htmlFor="doc-title">Title</Label><Input id="doc-title" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
            <div><Label htmlFor="doc-groups">Who can read it (comma separated groups)</Label><Input id="doc-groups" value={groups} onChange={(e) => setGroups(e.target.value)} /></div>
          </div>
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-signal"><FileUp className="size-4" />Upload .md, .txt or .pdf
            <input type="file" accept=".md,.txt,.pdf,text/plain,text/markdown,application/pdf" className="sr-only" onChange={(e) => onFile(e.target.files?.[0])} /></label>
          {pdf ? <p className="text-sm text-muted">PDF ready: {pdf.name}. Text is extracted on the server.</p> :
            <Textarea aria-label="Document text" rows={6} value={text} onChange={(e) => setText(e.target.value)} placeholder="Or paste Markdown or plain text" />}
          <Button onClick={() => add.mutate()} disabled={add.isPending || title.trim().length < 1 || (!pdf && text.trim().length < 20)}><Plus />Add document</Button>
        </section>
      ) : <p className="text-sm text-muted">This is a shared dataset. Create your own dataset to upload documents.</p>}
    </div>
  );
}

function EvaluateTab({ ds, cfg }: { ds: Dataset; cfg: RunCfg }) {
  const { user } = useAuth();
  const run = useMutation({ mutationFn: () => api.post<EvalOut>("/rag/evaluate", { dataset: ds.slug, ...cfg }), onError: (e) => toast.error(errorMessage(e)) });
  const r = run.data;
  if (!ds.questions.length) return <EmptyState title="No labelled questions">Evaluation needs questions with known relevant sources. The Northwind handbook dataset has 12.</EmptyState>;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-xl text-sm text-muted">Runs all {ds.questions.length} labelled questions with the current settings and measures whether the right sources come back. Change one setting at a time and compare runs in Evaluations.</p>
        <Button onClick={() => run.mutate()} disabled={!user || run.isPending}><FlaskConical />{run.isPending ? "Evaluating…" : "Run evaluation"}</Button>
      </div>
      {r && (
        <>
          <dl className="grid grid-cols-2 gap-4 rounded-lg border border-line p-4 sm:grid-cols-4">
            {Object.entries(r.metrics).map(([k, v]) => (
              <Metric key={k} label={metricLabel(k)} value={k.includes("latency") ? `${v} ms` : k === "mrr" ? v.toFixed(2) : pct(v)} />
            ))}
          </dl>
          <p className="text-sm text-muted">{r.passed} of {r.total} questions passed in {r.duration_ms} ms. <Link className="text-signal hover:underline" to={`/evaluations/${r.evaluation_id}`}>Saved to Evaluations</Link></p>
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-sm">
              <thead className="bg-panel-2 text-left text-muted"><tr><th className="px-3 py-2 font-medium">Question</th><th className="px-3 py-2 font-medium">Expected</th><th className="px-3 py-2 font-medium">Retrieved</th><th className="px-3 py-2 font-medium">Recall</th><th className="px-3 py-2 font-medium">Result</th></tr></thead>
              <tbody>{r.cases.map((c) => (
                <tr key={c.question} className="border-t border-line align-top">
                  <td className="px-3 py-2">{c.question}{c.groups.some((g) => g !== "everyone") && <span className="ml-1 text-xs text-tool">as {c.groups.join(", ")}</span>}
                    {c.answer && <p className="mt-1 text-xs text-muted">{c.answer.slice(0, 200)}</p>}</td>
                  <td className="px-3 py-2 font-mono text-xs">{c.relevant.join(", ") || "(none: should decline)"}</td>
                  <td className="px-3 py-2 font-mono text-xs">{c.retrieved_sources.map((s) => <span key={s} className={cn("block", c.relevant.includes(s) ? "text-pass" : "text-muted")}>{s}</span>)}</td>
                  <td className="px-3 py-2 tabular-nums">{pct(c.recall)}</td>
                  <td className="px-3 py-2"><Badge tone={c.passed ? "pass" : "fail"}>{c.passed ? "pass" : "fail"}</Badge></td>
                </tr>))}</tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function NewDataset() {
  const qc = useQueryClient();
  const [, setParams] = useSearchParams();
  const [name, setName] = useState("");
  const m = useMutation({
    mutationFn: () => api.post<{ slug: string }>("/rag/datasets", { name }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["rag-datasets"] }); setParams({ dataset: r.slug }); setName(""); toast.success("Dataset created. Add documents in the Documents tab."); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
      <Input aria-label="New dataset name" value={name} onChange={(e) => setName(e.target.value)} placeholder="New dataset name" className="h-8" />
      <Button size="sm" variant="secondary" type="submit" disabled={name.trim().length < 2 || m.isPending}><Plus />Create</Button>
    </form>
  );
}

export default function RagLab() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const opts = useQuery({ queryKey: ["rag-options"], queryFn: () => api.get<Options>("/rag/options") });
  const list = useQuery({ queryKey: ["rag-datasets"], queryFn: () => api.get<{ items: DatasetCard[] }>("/rag/datasets") });
  const key = params.get("dataset") ?? (list.data?.items.find((d) => d.slug === "northwind-handbook") ?? list.data?.items[0])?.slug;
  const ds = useQuery({ queryKey: ["rag-dataset", key], queryFn: () => api.get<Dataset>(`/rag/datasets/${key}`), enabled: !!key });
  const [cfg, setCfg] = useState<RunCfg | null>(null);
  const [prompt, setPrompt] = useState<{ system: string; user: string } | null>(null);
  useEffect(() => {
    if (opts.data && !cfg) setCfg({ ...opts.data.defaults, strategy: "hybrid", top_k: 4, rerank: true, generate: true });
    if (opts.data && !prompt) setPrompt(opts.data.default_prompt);
  }, [opts.data, cfg, prompt]);
  const datasets = useMemo(() => list.data?.items ?? [], [list.data]);

  if (opts.error || list.error) return <ErrorState error={opts.error ?? list.error} />;
  if (!opts.data || !cfg || !prompt || list.isLoading) return <PageSkeleton />;
  return (
    <div>
      <PageHeader title="RAG Engineering Lab" description="Build a retrieval pipeline step by step: chunk, embed, retrieve, rerank and answer with citations. Then measure it with recall and MRR instead of eyeballing." />
      <div className="grid gap-8 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <aside className="space-y-6 lg:sticky lg:top-20 lg:self-start">
          <div>
            <Label htmlFor="dataset">Dataset</Label>
            <Select id="dataset" value={key} onChange={(e) => setParams({ dataset: e.target.value })}>
              {datasets.map((d) => <option key={d.slug} value={d.slug}>{d.name}{d.mine ? " (yours)" : ""}</option>)}
            </Select>
            {user && <div className="mt-2"><NewDataset /></div>}
          </div>
          <ConfigPanel o={opts.data} cfg={cfg} set={setCfg} />
        </aside>
        <div className="min-w-0">
          {ds.isLoading ? <PageSkeleton /> : ds.error ? <ErrorState error={ds.error} /> : ds.data && (
            <>
              <p className="mb-4 text-sm text-muted">{ds.data.description}</p>
              <Tabs defaultValue="ask">
                <TabsList>
                  <TabsTrigger value="ask">Ask</TabsTrigger>
                  <TabsTrigger value="docs">Documents ({ds.data.documents.length})</TabsTrigger>
                  <TabsTrigger value="eval">Evaluate</TabsTrigger>
                  <TabsTrigger value="prompt">Answer prompt</TabsTrigger>
                </TabsList>
                <TabsContent value="ask"><AskTab ds={ds.data} cfg={cfg} prompt={prompt} /></TabsContent>
                <TabsContent value="docs"><DocumentsTab ds={ds.data} cfg={cfg} /></TabsContent>
                <TabsContent value="eval"><EvaluateTab ds={ds.data} cfg={cfg} /></TabsContent>
                <TabsContent value="prompt">
                  <div className="space-y-4">
                    <p className="text-sm text-muted">The generation prompt. Retrieved passages arrive as untrusted data: one Northwind document contains a planted instruction. Try weakening the system prompt and asking about vendor integrations.</p>
                    <div><Label htmlFor="rag-sys">System</Label><Textarea id="rag-sys" rows={6} className="font-mono text-[13px]" value={prompt.system} onChange={(e) => setPrompt({ ...prompt, system: e.target.value })} /></div>
                    <div><Label htmlFor="rag-user">User template (must include {"{{passages}}"} and {"{{question}}"})</Label><Textarea id="rag-user" rows={6} className="font-mono text-[13px]" value={prompt.user} onChange={(e) => setPrompt({ ...prompt, user: e.target.value })} /></div>
                    <Button variant="secondary" onClick={() => setPrompt(opts.data!.default_prompt)}>Reset to default</Button>
                  </div>
                </TabsContent>
              </Tabs>
              <div className="mt-8"><SimulatorNote /></div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
