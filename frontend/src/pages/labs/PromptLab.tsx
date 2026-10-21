import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitFork, Play, Save, Scale } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, formatDate, titleCase } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Textarea } from "@/components/ui/input";
import { CodeEditor } from "@/components/LazyEditor";
import { ErrorState, PageHeader } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { CheckList, type CheckResult, ModeBadge, SimulatorNote, pct } from "@/components/LabBits";

interface TemplateCard { slug: string; name: string; category: string; description: string; mine: boolean; versions: number; test_cases: number }
interface Version { id: string; version: number; system: string; user_template: string; variables: string[]; params: Params; change_note: string; created_at: string }
interface Params { temperature?: number; max_tokens?: number; json_schema?: Record<string, unknown> | null }
interface Assertion { type: string; value?: unknown; label?: string }
interface Case { id?: string; name: string; variables: Record<string, unknown>; assertions: Assertion[] }
interface Template { slug: string; name: string; category: string; description: string; editable: boolean; versions: Version[]; test_cases: Case[] }
interface RunOut { output: string; error: string | null; input_tokens: number; output_tokens: number; latency_ms: number; cost_usd: number | null;
  provider: string; model: string; mode: string; provider_label: string; checks: { results: CheckResult[]; passed: number; total: number } | null }
interface Variant { label: string; system: string; user_template: string; params: Params }
interface CompareOut { evaluation_id: string; mode: string; provider_label: string; best: string; cases: Case[]; variants: Variant[];
  summary: { variant: number; label: string; pass_rate: number; check_pass_rate: number | null; avg_input_tokens: number; avg_output_tokens: number; avg_latency_ms: number; cost_usd: number; errors: number }[];
  matrix: { variant: number; case: number; output: string; error: string | null; passed: boolean; checks: { results: CheckResult[] } }[] }

const CATEGORY: Record<string, string> = { rag: "RAG", "structured-output": "Structured output", agents: "Agents" };
const VAR = /{{\s*([A-Za-z_][\w.-]*)\s*}}/g;
const varsOf = (...t: string[]) => [...new Set(t.flatMap((s) => [...s.matchAll(VAR)].map((m) => m[1].split(".")[0])))];

function Library({ active }: { active?: string }) {
  const q = useQuery({ queryKey: ["prompt-templates"], queryFn: () => api.get<{ items: TemplateCard[]; categories: string[] }>("/prompts/templates") });
  const groups = useMemo(() => {
    const g: Record<string, TemplateCard[]> = {};
    q.data?.items.forEach((t) => (g[t.mine ? "Your copies" : CATEGORY[t.category] ?? titleCase(t.category)] ||= []).push(t));
    return g;
  }, [q.data]);
  return (
    <nav aria-label="Prompt templates" className="space-y-5">
      {Object.entries(groups).map(([g, items]) => (
        <div key={g}>
          <p className="mb-1 text-xs font-medium text-faint">{g}</p>
          <ul className="space-y-0.5">
            {items.map((t) => (
              <li key={t.slug}>
                <Link to={`/labs/prompts/${t.slug}`} className={cn("block rounded-md px-2.5 py-1.5 text-sm", t.slug === active ? "bg-panel-2 text-fg" : "text-muted hover:text-fg")}>
                  {t.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Workbench({ t }: { t: Template }) {
  const { user } = useAuth();
  const nav = useNavigate();
  const qc = useQueryClient();
  const latest = t.versions[0];
  const [system, setSystem] = useState(latest?.system ?? "");
  const [userT, setUserT] = useState(latest?.user_template ?? "");
  const [schema, setSchema] = useState(latest?.params?.json_schema ? JSON.stringify(latest.params.json_schema, null, 2) : "");
  const [temperature, setTemperature] = useState(latest?.params?.temperature ?? 0);
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(t.test_cases[0]?.variables ?? {}).map(([k, v]) => [k, String(v)])));
  const [activeCase, setActiveCase] = useState<number | null>(t.test_cases.length ? 0 : null);
  const [picked, setPicked] = useState<string[]>(() => t.versions.slice(0, 2).map((v) => v.id));
  const [includeEdits, setIncludeEdits] = useState(false);
  const [note, setNote] = useState("");
  const [casesJson, setCasesJson] = useState(JSON.stringify(t.test_cases.map(({ name, variables, assertions }) => ({ name, variables, assertions })), null, 2));
  useEffect(() => {
    const v = t.versions[0];
    setSystem(v?.system ?? ""); setUserT(v?.user_template ?? ""); setSchema(v?.params?.json_schema ? JSON.stringify(v.params.json_schema, null, 2) : "");
    setTemperature(v?.params?.temperature ?? 0);
    setValues(Object.fromEntries(Object.entries(t.test_cases[0]?.variables ?? {}).map(([k, val]) => [k, String(val)])));
    setPicked(t.versions.slice(0, 2).map((x) => x.id));
    setActiveCase(t.test_cases.length ? 0 : null);
    setCasesJson(JSON.stringify(t.test_cases.map(({ name, variables, assertions }) => ({ name, variables, assertions })), null, 2));
  }, [t.slug]); // eslint-disable-line react-hooks/exhaustive-deps

  const vars = varsOf(system, userT);
  const parsedSchema = (): Record<string, unknown> | null => {
    if (!schema.trim()) return null;
    try { return JSON.parse(schema); } catch { throw new Error("The JSON schema isn't valid JSON."); }
  };
  const current = (): Variant => ({ label: "Your edits", system, user_template: userT, params: { temperature, json_schema: parsedSchema() } });

  const run = useMutation({
    mutationFn: () => api.post<RunOut>("/prompts/run", { ...current(), variables: values, assertions: activeCase === null ? [] : t.test_cases[activeCase]?.assertions ?? [] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const compare = useMutation({
    mutationFn: () => {
      const variants: Variant[] = t.versions.filter((v) => picked.includes(v.id)).reverse()
        .map((v) => ({ label: `v${v.version}`, system: v.system, user_template: v.user_template, params: v.params ?? {} }));
      if (includeEdits) variants.push(current());
      return api.post<CompareOut>("/prompts/compare", { template_slug: t.slug, variants });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const fork = useMutation({
    mutationFn: () => api.post<{ slug: string }>(`/prompts/templates/${t.slug}/fork`),
    onSuccess: (r) => { toast.success("Copied to your templates. You can now save versions."); qc.invalidateQueries({ queryKey: ["prompt-templates"] }); nav(`/labs/prompts/${r.slug}`); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const saveVersion = useMutation({
    mutationFn: () => api.post<Version>(`/prompts/templates/${t.slug}/versions`, { ...current(), change_note: note }),
    onSuccess: (v) => { toast.success(`Saved version ${v.version}`); setNote(""); qc.invalidateQueries({ queryKey: ["prompt-template", t.slug] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const saveCases = useMutation({
    mutationFn: () => api.put(`/prompts/templates/${t.slug}/test-cases`, { cases: JSON.parse(casesJson) }),
    onSuccess: () => { toast.success("Test cases saved"); qc.invalidateQueries({ queryKey: ["prompt-template", t.slug] }); },
    onError: (e) => toast.error(e instanceof SyntaxError ? "Test cases aren't valid JSON." : errorMessage(e)),
  });

  const variantCount = picked.length + (includeEdits ? 1 : 0);
  return (
    <div className="min-w-0 space-y-10">
      <div className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-3xl font-semibold">{t.name}</h1>
            <Badge tone="outline">{CATEGORY[t.category] ?? titleCase(t.category)}</Badge>
          </div>
          <p className="mt-2 max-w-2xl text-muted">{t.description}</p>
        </div>
        {user && !t.editable && <Button variant="secondary" onClick={() => fork.mutate()} disabled={fork.isPending}><GitFork />Fork to edit</Button>}
      </div>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg font-semibold">Prompt</h2>
            <select aria-label="Load version" className="h-8 rounded-md border border-line bg-sunken px-2 text-sm"
              onChange={(e) => { const v = t.versions.find((x) => x.id === e.target.value); if (v) { setSystem(v.system); setUserT(v.user_template); setSchema(v.params?.json_schema ? JSON.stringify(v.params.json_schema, null, 2) : ""); } }}>
              {t.versions.map((v) => <option key={v.id} value={v.id}>Load v{v.version}: {v.change_note}</option>)}
            </select>
          </div>
          <div><Label htmlFor="sys">System instructions</Label><Textarea id="sys" rows={4} value={system} onChange={(e) => setSystem(e.target.value)} className="font-mono text-[13px]" /></div>
          <div><Label htmlFor="usr">User message template</Label><Textarea id="usr" rows={5} value={userT} onChange={(e) => setUserT(e.target.value)} className="font-mono text-[13px]" />
            <p className="mt-1 text-xs text-faint">Use {"{{variable}}"} placeholders. Variables found: {vars.length ? vars.join(", ") : "none"}.</p></div>
          <details>
            <summary className="cursor-pointer text-sm text-muted">Parameters and JSON schema (structured output)</summary>
            <div className="mt-3 space-y-3">
              <div className="flex items-center gap-3"><Label htmlFor="temp" className="mb-0">Temperature</Label>
                <Input id="temp" type="number" min={0} max={2} step={0.1} value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} className="w-24" /></div>
              <CodeEditor value={schema} onChange={setSchema} language="json" height={160} ariaLabel="JSON schema" />
              <p className="text-xs text-faint">Leave empty for free text. With a schema the model is asked for exactly that JSON shape.</p>
            </div>
          </details>
          {t.editable && (
            <div className="flex flex-wrap items-end gap-2 rounded-lg border border-line p-3">
              <div className="min-w-48 flex-1"><Label htmlFor="note">Change note</Label><Input id="note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="What changed and why" /></div>
              <Button variant="secondary" onClick={() => { try { parsedSchema(); saveVersion.mutate(); } catch (e) { toast.error((e as Error).message); } }} disabled={note.trim().length < 3 || saveVersion.isPending}><Save />Save as new version</Button>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <h2 className="font-display text-lg font-semibold">Try it</h2>
          {vars.map((v) => (
            <div key={v}><Label htmlFor={`var-${v}`}>{v}</Label>
              <Textarea id={`var-${v}`} rows={v.match(/passages|context|diff|transcript|invoice|email/) ? 5 : 2} value={values[v] ?? ""} onChange={(e) => { setValues({ ...values, [v]: e.target.value }); setActiveCase(null); }} /></div>
          ))}
          <div className="flex flex-wrap gap-2">
            {t.test_cases.map((c, i) => (
              <button key={c.name} aria-pressed={activeCase === i} onClick={() => { setValues(Object.fromEntries(Object.entries(c.variables).map(([k, v]) => [k, String(v)]))); setActiveCase(i); }}
                className={cn("rounded-full border px-2.5 py-0.5 text-xs", activeCase === i ? "border-signal text-fg" : "border-line text-muted hover:text-fg")}>
                {c.name}
              </button>
            ))}
          </div>
          <p className="text-xs text-faint">{activeCase === null ? "Custom input: no assertions are checked." : `Checks the assertions of "${t.test_cases[activeCase]?.name}".`}</p>
          {user ? (
            <Button onClick={() => { try { parsedSchema(); run.mutate(); } catch (e) { toast.error((e as Error).message); } }} disabled={run.isPending}><Play />{run.isPending ? "Running…" : "Run prompt"}</Button>
          ) : <p className="text-sm text-muted"><Link to="/login?next=/labs/prompts" className="text-signal hover:underline">Sign in</Link> to run prompts.</p>}
          {run.data && (
            <div className="space-y-3 rounded-lg border border-line bg-panel p-4" aria-live="polite">
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
                <ModeBadge mode={run.data.mode} label={run.data.provider_label} />
                <span>{run.data.input_tokens} in / {run.data.output_tokens} out tokens</span><span>{run.data.latency_ms} ms</span>
                <span>{run.data.cost_usd === null ? "cost unknown" : `$${run.data.cost_usd.toFixed(5)}`}</span>
              </div>
              {run.data.error ? <p className="text-sm text-fail">{run.data.error}</p> : <pre className="whitespace-pre-wrap rounded-md bg-sunken p-3 font-mono text-[13px]">{run.data.output}</pre>}
              {run.data.checks && <CheckList results={run.data.checks.results} />}
            </div>
          )}
          <SimulatorNote />
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="font-display text-lg font-semibold">Compare versions on the test cases</h2>
            <p className="text-sm text-muted">Runs each variant against all {t.test_cases.length} test cases and scores them with the assertions. Results are saved to Evaluations.</p>
          </div>
          <Button variant="secondary" onClick={() => { try { parsedSchema(); compare.mutate(); } catch (e) { toast.error((e as Error).message); } }} disabled={!user || variantCount < 1 || compare.isPending}>
            <Scale />{compare.isPending ? "Comparing…" : `Compare ${variantCount} variant${variantCount === 1 ? "" : "s"}`}
          </Button>
        </div>
        <div className="flex flex-wrap gap-3 text-sm">
          {t.versions.map((v) => (
            <label key={v.id} className="flex items-center gap-2 rounded-md border border-line px-3 py-1.5">
              <input type="checkbox" className="accent-[var(--signal)]" checked={picked.includes(v.id)}
                onChange={(e) => setPicked(e.target.checked ? [...picked, v.id].slice(-3) : picked.filter((x) => x !== v.id))} />
              v{v.version} <span className="text-muted">{v.change_note}</span>
            </label>
          ))}
          <label className="flex items-center gap-2 rounded-md border border-line px-3 py-1.5">
            <input type="checkbox" className="accent-[var(--signal)]" checked={includeEdits} onChange={(e) => setIncludeEdits(e.target.checked)} />Your current edits
          </label>
        </div>
        {compare.data && <CompareResult r={compare.data} />}
      </section>

      <section className="space-y-3">
        <h2 className="font-display text-lg font-semibold">Test cases</h2>
        {t.editable ? (
          <>
            <p className="text-sm text-muted">Edit as JSON. Assertion types: contains, not_contains, regex, not_regex, equals, one_of, json_valid, json_schema, max_words, min_words, max_chars.</p>
            <CodeEditor value={casesJson} onChange={setCasesJson} language="json" height={280} ariaLabel="Test cases" />
            <Button variant="secondary" onClick={() => saveCases.mutate()} disabled={saveCases.isPending}><Save />Save test cases</Button>
          </>
        ) : (
          <ul className="divide-y divide-line rounded-lg border border-line">
            {t.test_cases.map((c) => (
              <li key={c.name} className="grid gap-2 p-4 md:grid-cols-[12rem_1fr_1fr]">
                <span className="font-medium">{c.name}</span>
                <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-xs text-muted">{JSON.stringify(c.variables, null, 1).slice(0, 400)}</pre>
                <ul className="space-y-0.5 text-sm">{c.assertions.map((a, i) => <li key={i}><Badge tone="outline">{a.type}</Badge> <span className="text-muted">{a.label ?? (a.value !== undefined ? JSON.stringify(a.value).slice(0, 60) : "")}</span></li>)}</ul>
              </li>
            ))}
          </ul>
        )}
      </section>
      <p className="text-xs text-faint">Versions: {t.versions.map((v) => `v${v.version} (${formatDate(v.created_at)})`).join(", ")}</p>
    </div>
  );
}

function CompareResult({ r }: { r: CompareOut }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <ModeBadge mode={r.mode} label={r.provider_label} />
        <span>Best: <span className="font-medium">{r.best}</span></span>
        <Link to={`/evaluations/${r.evaluation_id}`} className="text-signal hover:underline">Open in Evaluations</Link>
      </div>
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel-2 text-left text-muted"><tr>
            <th className="px-3 py-2 font-medium">Variant</th><th className="px-3 py-2 font-medium">Cases passed</th><th className="px-3 py-2 font-medium">Checks passed</th>
            <th className="px-3 py-2 font-medium">Avg tokens in/out</th><th className="px-3 py-2 font-medium">Avg latency</th><th className="px-3 py-2 font-medium">Cost</th></tr></thead>
          <tbody>{r.summary.map((s) => (
            <tr key={s.label} className={cn("border-t border-line", s.label === r.best && "bg-pass/5")}>
              <td className="px-3 py-2 font-medium">{s.label}{s.label === r.best && <Badge tone="pass" className="ml-2">best</Badge>}</td>
              <td className="px-3 py-2 tabular-nums">{pct(s.pass_rate)}</td><td className="px-3 py-2 tabular-nums">{pct(s.check_pass_rate)}</td>
              <td className="px-3 py-2 tabular-nums">{s.avg_input_tokens} / {s.avg_output_tokens}</td><td className="px-3 py-2 tabular-nums">{s.avg_latency_ms} ms</td>
              <td className="px-3 py-2 tabular-nums">${s.cost_usd.toFixed(5)}</td></tr>))}</tbody>
        </table>
      </div>
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel-2 text-left text-muted"><tr><th className="px-3 py-2 font-medium">Test case</th>{r.variants.map((v) => <th key={v.label} className="px-3 py-2 font-medium">{v.label}</th>)}</tr></thead>
          <tbody>
            {r.cases.map((c, ci) => (
              <tr key={ci} className="border-t border-line align-top">
                <td className="px-3 py-2"><button className="text-left hover:text-signal" onClick={() => setOpen(open === ci ? null : ci)}>{c.name}</button></td>
                {r.variants.map((_, vi) => {
                  const m = r.matrix.find((x) => x.case === ci && x.variant === vi)!;
                  return (
                    <td key={vi} className="max-w-sm px-3 py-2">
                      <Badge tone={m.passed ? "pass" : "fail"}>{m.passed ? "pass" : "fail"}</Badge>
                      {open === ci && (
                        <div className="mt-2 space-y-2">
                          <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-sunken p-2 font-mono text-xs">{m.error ?? m.output}</pre>
                          <CheckList results={m.checks.results} className="text-xs" />
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-faint">Click a test case to see each variant's output and which assertions failed.</p>
    </div>
  );
}

export default function PromptLab() {
  const { slug } = useParams();
  const nav = useNavigate();
  const list = useQuery({ queryKey: ["prompt-templates"], queryFn: () => api.get<{ items: TemplateCard[] }>("/prompts/templates") });
  useEffect(() => { if (!slug && list.data?.items[0]) nav(`/labs/prompts/${list.data.items.find((t) => t.slug === "injection-safe-summary")?.slug ?? list.data.items[0].slug}`, { replace: true }); }, [slug, list.data, nav]);
  const t = useQuery({ queryKey: ["prompt-template", slug], queryFn: () => api.get<Template>(`/prompts/templates/${slug}`), enabled: !!slug });
  return (
    <div>
      <PageHeader title="Prompt Engineering Lab" description="Edit prompts, run them on test cases, and compare versions with assertions - the way prompt changes should ship: measured, versioned and reviewed." />
      <div className="grid gap-8 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-20 lg:self-start"><Library active={slug} /></aside>
        {t.isLoading || list.isLoading ? <PageSkeleton /> : t.error ? <ErrorState error={t.error} /> : t.data ? <Workbench t={t.data} /> : null}
      </div>
    </div>
  );
}
