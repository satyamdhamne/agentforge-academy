import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, FileCode2, Lock, Play, ShieldCheck, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AgentDetail as AD, AgentRun } from "@/lib/types";
import { LEVEL_LABEL, VERDICT_HELP, VERDICT_LABEL, cn, titleCase } from "@/lib/utils";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Markdown } from "@/components/Markdown";
import { Mermaid } from "@/components/Mermaid";
import { CodeBlock } from "@/components/CodeBlock";
import { TraceView } from "@/components/TraceView";
import { ErrorState, EmptyState } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { LevelPips } from "@/components/Meta";
import { VERDICT_TONE } from "./Agents";

type Dict = Record<string, unknown>;
const asList = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const asStr = (v: unknown) => (typeof v === "string" ? v : "");

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="font-display text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function List({ items }: { items: unknown[] }) {
  return <div className="prose-af"><ul>{items.map((i, n) => <li key={n}><Markdown className="[&_p]:m-0">{String(i)}</Markdown></li>)}</ul></div>;
}

function KV({ value }: { value: unknown }) {
  if (!value || typeof value !== "object") return <Markdown>{asStr(value)}</Markdown>;
  return (
    <dl className="space-y-2">
      {Object.entries(value as Dict).map(([k, v]) => (
        <div key={k}>
          <dt className="text-sm font-medium">{titleCase(k)}</dt>
          <dd className="text-sm text-muted">{Array.isArray(v) ? v.join(", ") : <Markdown className="[&_p]:m-0">{String(v)}</Markdown>}</dd>
        </div>
      ))}
    </dl>
  );
}

function PairTable({ rows, a, b, aLabel, bLabel }: { rows: unknown[]; a: string; b: string; aLabel: string; bLabel: string }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full text-left text-sm">
        <thead className="bg-panel-2 text-muted"><tr><th className="px-3 py-2 font-medium">{aLabel}</th><th className="px-3 py-2 font-medium">{bLabel}</th></tr></thead>
        <tbody>{rows.map((r, i) => { const d = r as Dict; return <tr key={i} className="border-t border-line align-top"><td className="px-3 py-2">{String(d[a])}</td><td className="px-3 py-2 text-muted">{String(d[b])}</td></tr>; })}</tbody>
      </table>
    </div>
  );
}

function FileBrowser({ slug, files }: { slug: string; files: string[] }) {
  const [path, setPath] = useState(files.find((f) => f.endsWith("/agent.py")) ?? files[0]);
  const f = useQuery({ queryKey: ["agent-file", slug, path], queryFn: () => api.get<{ path: string; language: string; content: string }>(`/agents/${slug}/files/${path}`), enabled: !!path });
  return (
    <div className="grid gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <ul className="max-h-[520px] space-y-0.5 overflow-auto rounded-lg border border-line p-1.5 font-mono text-xs scrollbar-thin" aria-label="Files">
        {files.map((p) => (
          <li key={p}>
            <button onClick={() => setPath(p)} className={cn("flex w-full items-center gap-1.5 rounded px-2 py-1 text-left", p === path ? "bg-panel-2 text-fg" : "text-muted hover:text-fg")}>
              <FileCode2 className="size-3.5 shrink-0" /><span className="truncate" title={p}>{p.replace("agents/agentforge_agents/", "")}</span>
            </button>
          </li>
        ))}
      </ul>
      <div className="min-w-0">
        <p className="mb-2 font-mono text-xs text-muted">{path}</p>
        {f.data ? <CodeBlock code={f.data.content} language={f.data.language} className="max-h-[520px] overflow-auto" /> : <div className="h-64 animate-pulse rounded bg-panel-2" />}
      </div>
    </div>
  );
}

function RunMetrics({ r }: { r: AgentRun }) {
  const items: [string, string][] = [
    ["Status", titleCase(r.status)], ["Provider", `${r.provider} / ${r.model}`], ["Model calls", String(r.llm_calls)], ["Tool calls", String(r.tool_calls)],
    ["Tokens", `${r.input_tokens} in, ${r.output_tokens} out`], ["Latency", `${r.latency_ms} ms`],
    ["Cost", r.cost_usd === null || r.cost_usd === undefined ? "Unknown - add MODEL_PRICES" : `$${r.cost_usd.toFixed(4)}`],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
      {items.map(([k, v]) => <div key={k}><dt className="text-xs text-muted">{k}</dt><dd className="break-words">{v}</dd></div>)}
    </dl>
  );
}

function RunView({ run, onDecided }: { run: AgentRun; onDecided?: (r: AgentRun) => void }) {
  const [note, setNote] = useState("");
  const decide = useMutation({
    mutationFn: (decision: "approve" | "reject") => api.post<AgentRun>(`/agents/runs/${run.id}/decision`, { decision, note }),
    onSuccess: (r) => { toast.success(r.status === "approved" ? "Action approved and applied" : "Action rejected"); onDecided?.(r); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="space-y-5">
      <RunMetrics r={run} />
      {run.is_mock && <p className="text-xs text-faint">Model responses come from the deterministic mock provider, so results are reproducible and cost nothing. Paid plans can use the server’s configured provider.</p>}
      {run.error && <p className="rounded-md border border-fail/30 bg-fail/5 p-3 text-sm text-fail">{run.error}</p>}
      {run.status === "awaiting_approval" && run.pending_actions && run.pending_actions.length > 0 && (
        <div className="space-y-3 rounded-lg border border-tool/50 bg-tool/5 p-4">
          <p className="flex items-center gap-2 font-medium"><ShieldCheck className="size-4 text-tool" />This run wants to change something outside the platform. Nothing happens until you approve.</p>
          {run.pending_actions.map((a, i) => (
            <div key={i} className="rounded-md border border-line bg-panel p-3">
              <p className="text-sm"><span className="font-mono">{a.tool}</span>{a.reason && <span className="text-muted"> - {a.reason}</span>}</p>
              <CodeBlock className="mt-2" code={JSON.stringify(a.arguments, null, 2)} language="json" />
            </div>
          ))}
          {run.id && (
            <div className="flex flex-wrap items-end gap-3">
              <Textarea aria-label="Decision note" rows={1} placeholder="Note for the audit log (optional)" value={note} onChange={(e) => setNote(e.target.value)} className="max-w-sm" />
              <Button onClick={() => decide.mutate("approve")} disabled={decide.isPending}>Approve and apply</Button>
              <Button variant="danger" onClick={() => decide.mutate("reject")} disabled={decide.isPending}>Reject</Button>
            </div>
          )}
        </div>
      )}
      {run.approval_result && (
        <div className="rounded-md border border-line p-3 text-sm">
          <p className="mb-1 font-medium">{run.status === "approved" ? "Approved" : "Rejected"}</p>
          <CodeBlock code={JSON.stringify(run.approval_result, null, 2)} language="json" />
        </div>
      )}
      <div>
        <h3 className="mb-2 text-sm font-medium">Trace <span className="font-mono text-xs font-normal text-faint">{run.trace_id}</span></h3>
        <TraceView spans={run.trace} />
      </div>
      {run.output && <div><h3 className="mb-2 text-sm font-medium">Output</h3><CodeBlock code={JSON.stringify(run.output, null, 2)} language="json" className="max-h-[480px] overflow-auto" /></div>}
    </div>
  );
}

function RunPanel({ agent }: { agent: AD }) {
  const { user } = useAuth();
  const [idx, setIdx] = useState(0);
  const [input, setInput] = useState(() => JSON.stringify(agent.examples[0] ?? {}, null, 2));
  const [run, setRun] = useState<AgentRun | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: (body: Dict) => api.post<AgentRun>(`/agents/${agent.slug}/runs`, body),
    onSuccess: setRun,
    onError: (e) => toast.error(errorMessage(e)),
  });
  const go = () => {
    try { const parsed = JSON.parse(input); setParseError(null); m.mutate({ input: parsed }); }
    catch (e) { setParseError(`Input isn’t valid JSON: ${(e as Error).message}`); }
  };
  if (!user) return <EmptyState title="Sign in to run this agent" action={<Button asChild><Link to={`/login?next=/agents/${agent.slug}`}>Sign in</Link></Button>}>Runs are recorded with a full trace so you can inspect every step.</EmptyState>;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted">Start from an example</span>
        {agent.examples.map((_, i) => (
          <Button key={i} size="sm" variant={i === idx ? "secondary" : "ghost"} onClick={() => { setIdx(i); setInput(JSON.stringify(agent.examples[i], null, 2)); setRun(null); }}>Example {i + 1}</Button>
        ))}
      </div>
      <div>
        <label htmlFor="agent-input" className="mb-1.5 block text-sm font-medium">Input (validated against the agent’s schema)</label>
        <Textarea id="agent-input" rows={12} value={input} onChange={(e) => setInput(e.target.value)} className="font-mono text-xs" spellCheck={false} />
        {parseError && <p className="mt-1 text-sm text-fail">{parseError}</p>}
      </div>
      <Button onClick={go} disabled={m.isPending}><Play />{m.isPending ? "Running…" : "Run agent"}</Button>
      {run && <RunView run={run} onDecided={setRun} />}
    </div>
  );
}

function RunEval({ slug }: { slug: string }) {
  const { user } = useAuth();
  const m = useMutation({
    mutationFn: () => api.post<NonNullable<AD["eval_report"]> & { evaluation_id: string }>(`/agents/${slug}/evaluate`),
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!user) return null;
  return (
    <div className="space-y-4 rounded-lg border border-line p-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="mr-auto text-sm text-muted">Run the agent's test suite yourself. Results are saved to your Evaluations.</p>
        <Button size="sm" variant="secondary" onClick={() => m.mutate()} disabled={m.isPending}><Play />{m.isPending ? "Running…" : "Run evaluation"}</Button>
      </div>
      {m.data && (
        <div className="space-y-3">
          <p className="text-sm"><span className="font-medium tabular-nums">{m.data.passed}/{m.data.cases}</span> cases passed just now.{" "}
            <Link className="text-signal hover:underline" to={`/evaluations/${m.data.evaluation_id}`}>Open in Evaluations</Link></p>
          <ul className="space-y-1 text-sm">{m.data.results.map((c) => (
            <li key={c.id} className="flex items-center gap-2">{c.passed ? <CheckCircle2 className="size-4 text-pass" /> : <XCircle className="size-4 text-fail" />}<span className="font-mono text-xs">{c.id}</span></li>
          ))}</ul>
        </div>
      )}
    </div>
  );
}

function EvalReport({ r, criteria }: { r: NonNullable<AD["eval_report"]>; criteria?: string }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-4">
        <span className="font-display text-3xl font-semibold tabular-nums">{r.passed}/{r.cases}</span>
        <span className="text-muted">cases passed with the {r.provider} provider</span>
      </div>
      {criteria && <p className="text-sm text-muted">{criteria}</p>}
      <ul className="divide-y divide-line rounded-lg border border-line">
        {r.results.map((c) => (
          <li key={c.id} className="px-4 py-3">
            <details>
              <summary className="flex cursor-pointer items-center gap-2 text-sm">
                {c.passed ? <CheckCircle2 className="size-4 text-pass" /> : <XCircle className="size-4 text-fail" />}
                <span className="font-mono">{c.id}</span>
                <span className="ml-auto text-xs text-muted">{c.checks.length} checks</span>
              </summary>
              <ul className="mt-2 space-y-1 pl-6 font-mono text-xs">
                {c.checks.map((k, i) => <li key={i} className={k.passed ? "text-muted" : "text-fail"}>{k.passed ? "✓" : "✗"} {k.check}</li>)}
              </ul>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function AgentDetail() {
  const { slug = "" } = useParams();
  const q = useQuery({ queryKey: ["agent", slug], queryFn: () => api.get<AD>(`/agents/${slug}`) });
  if (q.isLoading) return <PageSkeleton />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const a = q.data!;
  const bp = a.blueprint as Dict;
  const impl = a.has_reference_impl;
  const fw = bp.framework as Dict | undefined;

  return (
    <div>
      <Link to="/agents" className="text-sm text-muted hover:text-fg">AI Agent Library</Link>
      <div className="mt-2 flex flex-wrap items-start gap-x-4 gap-y-2">
        <h1 className="text-3xl font-semibold leading-tight sm:text-4xl">{a.name}</h1>
        {impl ? <Badge tone="pass" className="mt-2">Runnable reference implementation</Badge> : <Badge className="mt-2">Blueprint</Badge>}
      </div>
      <p className="mt-3 max-w-3xl text-lg text-muted">{a.summary}</p>
      <dl className="mt-5 flex flex-wrap gap-x-8 gap-y-3 text-sm">
        <div><dt className="text-xs text-muted">Category</dt><dd>{a.category}</dd></div>
        <div><dt className="text-xs text-muted">Level</dt><dd><LevelPips level={a.level} /></dd></div>
        <div><dt className="text-xs text-muted">Estimated build time</dt><dd>~{a.build_hours} hours</dd></div>
        <div><dt className="text-xs text-muted">Recommended approach</dt><dd><Badge tone={VERDICT_TONE[a.verdict]}>{VERDICT_LABEL[a.verdict]}</Badge></dd></div>
        {fw && <div><dt className="text-xs text-muted">Framework</dt><dd>{String(fw.choice)}</dd></div>}
        {a.eval_report && <div><dt className="text-xs text-muted">Evaluation</dt><dd className="tabular-nums">{a.eval_report.passed}/{a.eval_report.cases} cases pass</dd></div>}
      </dl>

      {a.locked ? (
        <div className="mt-10"><EmptyState title="This blueprint is part of the Pro plan" action={<Button asChild><Link to="/pricing"><Lock />See plans</Link></Button>} /></div>
      ) : (
        <Tabs defaultValue="overview" className="mt-10">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="architecture">Architecture</TabsTrigger>
            {impl && <TabsTrigger value="prompts">Prompts & tools</TabsTrigger>}
            {impl && <TabsTrigger value="code">Code</TabsTrigger>}
            {impl && <TabsTrigger value="eval">Evaluation</TabsTrigger>}
            {a.runnable && <TabsTrigger value="run">Run it</TabsTrigger>}
            <TabsTrigger value="production">Production</TabsTrigger>
            <TabsTrigger value="practice">Practice</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="max-w-3xl space-y-8">
            <Block title="Problem"><Markdown>{asStr(bp.problem)}</Markdown></Block>
            {bp.business_value ? <Block title="Business value"><Markdown>{asStr(bp.business_value)}</Markdown></Block> : null}
            <Block title={`Why ${VERDICT_LABEL[a.verdict].toLowerCase()}${a.verdict === "agent" ? "" : ", not an autonomous agent"}`}>
              <p className="text-sm text-muted">{VERDICT_HELP[a.verdict]}</p>
              <Markdown>{asStr(bp.verdict_reasoning)}</Markdown>
            </Block>
            {asList(bp.inputs).length > 0 && (
              <div className="grid gap-8 sm:grid-cols-2">
                <Block title="Inputs"><List items={asList(bp.inputs)} /></Block>
                <Block title="Outputs"><List items={asList(bp.outputs)} /></Block>
              </div>
            )}
            {asList(bp.prerequisites).length > 0 && <Block title="Prerequisites"><List items={asList(bp.prerequisites)} /></Block>}
            {fw && <Block title="Framework decision"><KV value={fw} /></Block>}
            {bp.model_selection ? <Block title="Model selection"><KV value={bp.model_selection} /></Block> : null}
            {asList(bp.suggested_tools).length > 0 && (
              <Block title="Suggested tools">
                <ul className="flex flex-wrap gap-2">{asList(bp.suggested_tools).map((t) => <li key={String(t)}><Badge tone="outline" className="font-mono">{String(t)}</Badge></li>)}</ul>
              </Block>
            )}
            {!impl && <p className="rounded-lg border border-dashed border-line-strong p-4 text-sm text-muted">This entry is a blueprint: the problem, the recommended approach, the main risk and a reference architecture. It doesn’t have a runnable reference implementation yet. The ten runnable agents show the full pattern end to end.</p>}
          </TabsContent>

          <TabsContent value="architecture" className="max-w-4xl space-y-8">
            {asStr(bp.architecture_mermaid) && <Mermaid chart={asStr(bp.architecture_mermaid)} />}
            {asList(bp.data_flow).length > 0 && (
              <Block title="Data flow">
                <ol className="list-decimal space-y-1.5 pl-5 text-sm marker:text-faint">{asList(bp.data_flow).map((s, i) => <li key={i}><Markdown className="[&_p]:m-0">{String(s)}</Markdown></li>)}</ol>
              </Block>
            )}
            {bp.state_memory ? <Block title="State and memory"><Markdown>{asStr(bp.state_memory)}</Markdown></Block> : null}
          </TabsContent>

          {impl && (
            <TabsContent value="prompts" className="space-y-8">
              <Block title="Prompt templates">
                <p className="text-sm text-muted">Read from the implementation, so they never drift from what actually runs.</p>
                {asList(bp.prompts).map((p) => { const d = p as Dict; return <div key={String(d.name)}><p className="mb-1 font-mono text-xs text-muted">{String(d.name)}</p><CodeBlock code={String(d.template)} language="markup" /></div>; })}
              </Block>
              <Block title="Tools and steps">
                <ul className="space-y-3">
                  {asList(bp.tools).map((t) => {
                    const d = t as Dict;
                    return (
                      <li key={String(d.name)} className="rounded-lg border border-line p-3">
                        <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-sm">{String(d.name)}</span><Badge tone={String(d.kind).includes("approval") ? "tool" : String(d.kind).includes("model") ? "llm" : "neutral"}>{String(d.kind)}</Badge></div>
                        {d.description ? <p className="mt-1 text-sm text-muted">{String(d.description)}</p> : null}
                        {d.schema ? <CodeBlock className="mt-2" code={JSON.stringify(d.schema, null, 2)} language="json" /> : d.signature ? <p className="mt-1 font-mono text-xs text-faint">{String(d.signature)}</p> : null}
                      </li>
                    );
                  })}
                </ul>
              </Block>
              {bp.input_schema ? <Block title="Input schema"><CodeBlock code={JSON.stringify(bp.input_schema, null, 2)} language="json" /></Block> : null}
            </TabsContent>
          )}

          {impl && (
            <TabsContent value="code" className="space-y-8">
              <Block title="Project structure"><CodeBlock code={asStr(bp.folder_structure)} language="text" showCopy={false} /></Block>
              <Block title="Source"><FileBrowser slug={a.slug} files={a.files} /></Block>
              <div className="grid gap-8 lg:grid-cols-2">
                <Block title="Install"><CodeBlock code={asStr(bp.install)} language="bash" /></Block>
                <Block title="Run locally"><CodeBlock code={asStr(bp.run_local)} language="bash" /></Block>
              </div>
              <Block title="Environment variables"><PairTable rows={asList(bp.env_vars)} a="name" b="description" aLabel="Variable" bLabel="Purpose" /></Block>
              {bp.tests ? <Block title="Tests"><KV value={bp.tests} /></Block> : null}
            </TabsContent>
          )}

          {impl && (
            <TabsContent value="eval">
              <div className="space-y-8">
                <RunEval slug={a.slug} />
                {a.eval_report ? <EvalReport r={a.eval_report} criteria={asStr((bp.evaluation as Dict | undefined)?.criteria)} /> : <p className="text-muted">No evaluation report yet.</p>}
              </div>
            </TabsContent>
          )}

          {a.runnable && (
            <TabsContent value="run" className="space-y-10">
              <RunPanel agent={a} />
              {a.example_runs.length > 0 && (
                <Block title="Recorded example runs">
                  {a.example_runs.map((r, i) => (
                    <details key={i} className="rounded-lg border border-line p-4">
                      <summary className="cursor-pointer text-sm font-medium">Example {i + 1}: {titleCase(r.status)}, {r.latency_ms} ms</summary>
                      <div className="mt-4"><RunView run={{ ...r, id: undefined }} /></div>
                    </details>
                  ))}
                </Block>
              )}
            </TabsContent>
          )}

          <TabsContent value="production" className="max-w-4xl space-y-8">
            <Block title="Security threats and mitigations"><PairTable rows={asList(bp.security)} a="threat" b="mitigation" aLabel="Threat" bLabel="Mitigation" /></Block>
            {bp.cost_latency ? <Block title="Cost and latency"><Markdown>{asStr(bp.cost_latency)}</Markdown></Block> : null}
            {bp.deployment ? <Block title="Deployment"><Markdown>{asStr(bp.deployment)}</Markdown></Block> : null}
            {bp.observability ? <Block title="Observability and debugging"><Markdown>{asStr(bp.observability)}</Markdown></Block> : null}
            {asList(bp.failure_modes).length > 0 && <Block title="Common failure modes"><PairTable rows={asList(bp.failure_modes)} a="mode" b="mitigation" aLabel="Failure" bLabel="Mitigation" /></Block>}
            {asList(bp.improvements).length > 0 && <Block title="Improvements"><List items={asList(bp.improvements)} /></Block>}
            {asList(bp.production_checklist).length > 0 && (
              <Block title="Production checklist">
                <ul className="space-y-1.5 text-sm">{asList(bp.production_checklist).map((c) => <li key={String(c)} className="flex gap-2"><span aria-hidden className="mt-1 size-3 shrink-0 rounded-sm border border-line-strong" />{String(c)}</li>)}</ul>
              </Block>
            )}
          </TabsContent>

          <TabsContent value="practice" className="max-w-3xl space-y-8">
            <Block title="Three progressive challenges">
              <ol className="space-y-3">
                {asList(bp.challenges).map((c, i) => {
                  const d = c as Dict;
                  return (
                    <li key={i} className="flex gap-3 rounded-lg border border-line p-4">
                      <span className="font-mono text-sm text-faint">{i + 1}</span>
                      <div><p className="font-medium">{String(d.title)} <span className="ml-1 text-xs font-normal text-muted">{LEVEL_LABEL[String(d.level)]}</span></p><p className="mt-1 text-sm text-muted">{String(d.description)}</p></div>
                    </li>
                  );
                })}
              </ol>
            </Block>
            <Block title="Interview questions">
              <div className="divide-y divide-line border-y border-line">
                {asList(bp.interview_questions).map((x, i) => {
                  const d = x as Dict;
                  return <details key={i} className="py-3"><summary className="cursor-pointer font-medium">{String(d.q)}</summary><p className="mt-2 text-muted">{String(d.a)}</p></details>;
                })}
              </div>
            </Block>
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
