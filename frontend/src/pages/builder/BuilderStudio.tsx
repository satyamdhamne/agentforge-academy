import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addEdge, Background, Controls, Handle, MiniMap, Position, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState,
  type Connection, type Edge, type Node, type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AlertTriangle, Ban, Check, CircleX, Pause, Play, Save, SkipForward, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { ErrorState } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { CheckList, ModeBadge } from "@/components/LabBits";

/* eslint-disable @typescript-eslint/no-explicit-any */
interface NodeType { type: string; label: string; description: string; color: string; defaults: Record<string, any> }
interface ToolInfo { name: string; description: string; args: Record<string, string>; side_effect: boolean }
interface Catalog { items: NodeType[]; tools: ToolInfo[]; budget: Record<string, number> }
interface GNode { key: string; type: string; config: Record<string, any>; position: { x: number; y: number } }
interface GEdge { source: string; target: string; handle?: string | null }
interface Issue { level: "error" | "warning"; message: string; node: string | null }
interface Workflow { id: string; name: string; description: string; version: number; nodes: GNode[]; edges: GEdge[]; issues: Issue[]; sample_input: Record<string, any> }
interface TraceRow { node: string; type: string; status: string; start_ms: number; duration_ms: number; output?: any; error?: string | null }
interface Run { id: string; status: string; mode: string; input: any; output: any; state: Record<string, any>; trace: TraceRow[]; node_status: Record<string, string>;
  pending: { node: string; message: string; next_actions: { node: string; tool: string; side_effect: boolean; args: Record<string, any> }[] } | null;
  steps: number; llm_calls: number; input_tokens: number; output_tokens: number; cost_usd: number | null; latency_ms: number; error: string | null }

type FlowData = { type: string; label: string; color: string; status?: string; issue?: "error" | "warning"; summary: string };

const COLOR: Record<string, string> = { signal: "border-signal/60", llm: "border-llm/70", tool: "border-tool/70", pass: "border-pass/60", fail: "border-fail/60", muted: "border-line-strong" };
const DOT: Record<string, string> = { signal: "bg-signal", llm: "bg-llm", tool: "bg-tool", pass: "bg-pass", fail: "bg-fail", muted: "bg-muted" };
const STATUS: Record<string, string> = { done: "ring-2 ring-pass/70", failed: "ring-2 ring-fail", paused: "ring-2 ring-tool animate-pulse", skipped: "opacity-50", running: "ring-2 ring-signal" };

function summarize(type: string, c: Record<string, any>): string {
  switch (type) {
    case "input": return (c.fields ?? []).map((f: any) => f.name).join(", ");
    case "prompt": return c.template ?? "";
    case "llm": return c.prompt ?? "";
    case "tool": return c.tool ?? "";
    case "retrieval": return `${c.dataset} top ${c.top_k}`;
    case "condition": return `${c.left} ${c.op} ${c.right ?? ""}`;
    case "memory": return `${c.mode} ${c.key}`;
    case "human_approval": return c.message ?? "";
    case "evaluation": return `${(c.checks ?? []).length} checks`;
    case "output": return c.value ?? "";
    default: return "";
  }
}

const FlowNode = memo(function FlowNode({ id, data, selected }: NodeProps<Node<FlowData>>) {
  return (
    <div className={cn("w-48 rounded-lg border-2 bg-panel px-3 py-2 text-left shadow-sm", COLOR[data.color] ?? "border-line", selected && "outline outline-2 outline-offset-2 outline-signal", data.status && STATUS[data.status])}>
      {data.type !== "input" && <Handle type="target" position={Position.Left} className="!h-2.5 !w-2.5 !border-line-strong !bg-panel-2" />}
      <div className="flex items-center gap-1.5 text-[11px] text-muted">
        <span className={cn("size-2 rounded-full", DOT[data.color])} />{data.label}
        {data.issue && <AlertTriangle className={cn("ml-auto size-3.5", data.issue === "error" ? "text-fail" : "text-tool")} />}
        {data.status && !data.issue && <span className="ml-auto">{data.status}</span>}
      </div>
      <div className="mt-0.5 truncate font-mono text-[13px] text-fg">{id}</div>
      <div className="truncate text-[11px] text-faint">{data.summary}</div>
      {data.type === "condition" ? (
        <>
          <Handle id="true" type="source" position={Position.Right} style={{ top: "35%" }} className="!h-2.5 !w-2.5 !border-pass !bg-pass" />
          <Handle id="false" type="source" position={Position.Right} style={{ top: "75%" }} className="!h-2.5 !w-2.5 !border-fail !bg-fail" />
          <span className="pointer-events-none absolute -right-9 top-[24%] text-[10px] text-pass">true</span>
          <span className="pointer-events-none absolute -right-9 top-[64%] text-[10px] text-fail">false</span>
        </>
      ) : data.type !== "output" && <Handle type="source" position={Position.Right} className="!h-2.5 !w-2.5 !border-line-strong !bg-panel-2" />}
    </div>
  );
});
const nodeTypes = { af: FlowNode };

function toFlow(g: GNode[], cat: Catalog): Node<FlowData>[] {
  return g.map((n) => {
    const t = cat.items.find((x) => x.type === n.type);
    return { id: n.key, type: "af", position: n.position ?? { x: 0, y: 0 }, data: { type: n.type, label: t?.label ?? n.type, color: t?.color ?? "muted", summary: summarize(n.type, n.config), config: n.config } as FlowData & { config: any } };
  });
}
const edgeStyle = (h?: string | null) => (h === "true" ? { stroke: "var(--pass)" } : h === "false" ? { stroke: "var(--fail)" } : undefined);
function toFlowEdges(g: GEdge[]): Edge[] {
  return g.map((e) => ({ id: `${e.source}-${e.handle ?? ""}-${e.target}`, source: e.source, target: e.target, sourceHandle: e.handle ?? undefined, style: edgeStyle(e.handle), label: e.handle ?? undefined }));
}

/* ------------------------------------------------------------ config forms */

function JsonField({ label, value, onChange, rows = 5 }: { label: string; value: any; onChange: (v: any) => void; rows?: number }) {
  const [text, setText] = useState(() => JSON.stringify(value ?? null, null, 2));
  const [bad, setBad] = useState(false);
  return (
    <div>
      <Label>{label}</Label>
      <Textarea rows={rows} className={cn("font-mono text-xs", bad && "border-fail")} value={text}
        onChange={(e) => { setText(e.target.value); try { onChange(e.target.value.trim() ? JSON.parse(e.target.value) : null); setBad(false); } catch { setBad(true); } }} />
      {bad && <p className="mt-1 text-xs text-fail">Not valid JSON yet; the last valid value is kept.</p>}
    </div>
  );
}

function ConfigForm({ type, c, set, tools }: { type: string; c: Record<string, any>; set: (c: Record<string, any>) => void; tools: ToolInfo[] }) {
  const text = (k: string, label: string, rows = 3, mono = true) => (
    <div key={k}><Label htmlFor={`cfg-${k}`}>{label}</Label><Textarea id={`cfg-${k}`} rows={rows} className={cn(mono && "font-mono text-xs")} value={c[k] ?? ""} onChange={(e) => set({ ...c, [k]: e.target.value })} /></div>
  );
  const num = (k: string, label: string, step = 1) => (
    <div key={k}><Label htmlFor={`cfg-${k}`}>{label}</Label><Input id={`cfg-${k}`} type="number" step={step} value={c[k] ?? 0} onChange={(e) => set({ ...c, [k]: Number(e.target.value) })} /></div>
  );
  switch (type) {
    case "input": return <JsonField label="Fields (name, label, type text|number|json, required)" value={c.fields} onChange={(v) => set({ ...c, fields: v })} rows={8} />;
    case "prompt": return text("template", "Template", 6);
    case "llm": return (<>{text("system", "System", 4)}{text("prompt", "Prompt", 5)}<div className="grid grid-cols-2 gap-2">{num("temperature", "Temperature", 0.1)}{num("max_tokens", "Max tokens", 16)}</div>
      <JsonField label="JSON schema (optional, for structured output)" value={c.json_schema ?? null} onChange={(v) => set({ ...c, json_schema: v })} /></>);
    case "tool": {
      const t = tools.find((x) => x.name === c.tool);
      return (<>
        <div><Label htmlFor="cfg-tool">Tool</Label><Select id="cfg-tool" value={c.tool} onChange={(e) => set({ ...c, tool: e.target.value, args: Object.fromEntries(Object.keys(tools.find((x) => x.name === e.target.value)?.args ?? {}).map((a) => [a, ""])) })}>
          {tools.map((x) => <option key={x.name} value={x.name}>{x.name}{x.side_effect ? " (side effect)" : ""}</option>)}</Select>
          {t && <p className="mt-1 text-xs text-faint">{t.description}</p>}
          {t?.side_effect && <p className="mt-1 text-xs text-tool">Has side effects: every path into this node must pass a Human approval node.</p>}</div>
        {Object.entries(t?.args ?? {}).map(([a, desc]) => (
          <div key={a}><Label htmlFor={`arg-${a}`}>{a}</Label><Input id={`arg-${a}`} className="font-mono text-xs" value={c.args?.[a] ?? ""} onChange={(e) => set({ ...c, args: { ...c.args, [a]: e.target.value } })} />
            <p className="mt-0.5 text-xs text-faint">{desc}</p></div>
        ))}
      </>);
    }
    case "retrieval": return (<>
      <div><Label htmlFor="cfg-dataset">Dataset</Label><Input id="cfg-dataset" value={c.dataset ?? ""} onChange={(e) => set({ ...c, dataset: e.target.value })} /></div>
      {text("query", "Query", 2)}<div className="grid grid-cols-2 gap-2">{num("top_k", "Top k")}
        <div><Label htmlFor="cfg-strategy">Strategy</Label><Select id="cfg-strategy" value={c.strategy} onChange={(e) => set({ ...c, strategy: e.target.value })}>
          {["hybrid", "vector", "keyword"].map((s) => <option key={s}>{s}</option>)}</Select></div></div></>);
    case "condition": return (<>{text("left", "Value", 2)}
      <div><Label htmlFor="cfg-op">Operator</Label><Select id="cfg-op" value={c.op} onChange={(e) => set({ ...c, op: e.target.value })}>
        {["equals", "not_equals", "contains", "not_contains", "gt", "lt", "exists", "is_true"].map((o) => <option key={o}>{o}</option>)}</Select></div>
      {!["exists", "is_true"].includes(c.op) && text("right", "Compare with", 1)}
      <p className="text-xs text-faint">Connect the green handle for true and the red one for false.</p></>);
    case "memory": return (<>
      <div><Label htmlFor="cfg-key">Key</Label><Input id="cfg-key" value={c.key ?? ""} onChange={(e) => set({ ...c, key: e.target.value })} /></div>
      <div><Label htmlFor="cfg-mode">Mode</Label><Select id="cfg-mode" value={c.mode} onChange={(e) => set({ ...c, mode: e.target.value })}>{["set", "append", "get"].map((m) => <option key={m}>{m}</option>)}</Select></div>
      {c.mode !== "get" && text("value", "Value", 3)}</>);
    case "human_approval": return text("message", "Message shown to the approver", 3, false);
    case "evaluation": return (<>{text("target", "Value to check", 2)}
      <JsonField label="Checks (same types as the Prompt Lab assertions)" value={c.checks} onChange={(v) => set({ ...c, checks: v })} rows={6} />
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-[var(--signal)]" checked={!!c.stop_on_fail} onChange={(e) => set({ ...c, stop_on_fail: e.target.checked })} />Stop the run if a check fails</label></>);
    case "output": return text("value", "Value", 4);
    default: return <JsonField label="Config" value={c} onChange={set} />;
  }
}

/* ------------------------------------------------------------ run panel */

function RunPanel({ run, onDecide, onCancel, busy }: { run: Run; onDecide: (d: "approve" | "reject", note: string) => void; onCancel: () => void; busy: boolean }) {
  const [note, setNote] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const tone = run.status === "succeeded" ? "pass" : run.status === "awaiting_approval" ? "tool" : ["failed", "rejected"].includes(run.status) ? "fail" : "neutral";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <Badge tone={tone as any}>{run.status.replace("_", " ")}</Badge><ModeBadge mode={run.mode} />
        <span>{run.steps} steps</span><span>{run.llm_calls} model calls</span><span>{run.input_tokens + run.output_tokens} tokens</span><span>{run.latency_ms} ms</span>
        {["awaiting_approval", "running"].includes(run.status) && <Button size="sm" variant="ghost" className="ml-auto" onClick={onCancel} disabled={busy}><Ban />Cancel run</Button>}
      </div>
      {run.error && <p className="text-sm text-fail">{run.error}</p>}
      {run.pending && run.status === "awaiting_approval" && (
        <div className="space-y-3 rounded-lg border border-tool/50 bg-tool/5 p-3">
          <p className="text-sm font-medium">Waiting for approval at <span className="font-mono">{run.pending.node}</span></p>
          <p className="text-sm">{run.pending.message}</p>
          {run.pending.next_actions.length > 0 && (
            <div className="text-sm"><p className="text-muted">If approved, these will run next:</p>
              <ul className="mt-1 space-y-1">{run.pending.next_actions.map((a) => (
                <li key={a.node} className="rounded bg-sunken p-2 font-mono text-xs">{a.tool}{a.side_effect && <Badge tone="tool" className="ml-2">side effect</Badge>}<pre className="mt-1 whitespace-pre-wrap">{JSON.stringify(a.args, null, 2)}</pre></li>
              ))}</ul></div>
          )}
          <Input aria-label="Decision note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note for the audit log (optional)" />
          <div className="flex gap-2"><Button size="sm" onClick={() => onDecide("approve", note)} disabled={busy}><Check />Approve</Button>
            <Button size="sm" variant="danger" onClick={() => onDecide("reject", note)} disabled={busy}><X />Reject</Button></div>
        </div>
      )}
      {run.output && (
        <div><p className="mb-1 text-xs text-muted">Output</p>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-sunken p-2 font-mono text-xs">{Object.values(run.output as Record<string, any>).map((o: any) => (typeof o?.value === "string" ? o.value : JSON.stringify(o?.value ?? o, null, 2))).join("\n\n")}</pre></div>
      )}
      <div>
        <p className="mb-1 text-xs text-muted">Trace</p>
        <ol className="space-y-1">
          {run.trace.map((t, i) => (
            <li key={i}>
              <button className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left text-xs hover:bg-panel-2" onClick={() => setOpen(open === i ? null : i)} aria-expanded={open === i}>
                {["ok", "approved"].includes(t.status) ? <Check className="size-3.5 text-pass" /> : ["error", "rejected"].includes(t.status) ? <CircleX className="size-3.5 text-fail" />
                  : t.status === "paused" ? <Pause className="size-3.5 text-tool" /> : <SkipForward className="size-3.5 text-faint" />}
                <span className={cn("font-mono", t.status === "skipped" && "text-faint")}>{t.node}</span><span className="text-faint">{t.status === "ok" ? t.type : `${t.type}, ${t.status}`}</span><span className="ml-auto tabular-nums text-muted">{t.duration_ms} ms</span>
              </button>
              {open === i && (
                <div className="mb-2 ml-6 space-y-1">
                  {t.error && <p className="text-xs text-fail">{t.error}</p>}
                  {t.output?.checks?.results ? <CheckList results={t.output.checks.results} className="text-xs" /> : null}
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-sunken p-2 font-mono text-[11px]">{typeof t.output === "string" ? t.output : JSON.stringify(t.output, null, 2)}</pre>
                </div>
              )}
            </li>
          ))}
        </ol>
      </div>
      <details><summary className="cursor-pointer text-xs text-muted">Run state</summary>
        <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-sunken p-2 font-mono text-[11px]">{JSON.stringify(run.state, null, 2)}</pre></details>
    </div>
  );
}

/* ------------------------------------------------------------ studio */

function Studio({ wf, cat }: { wf: Workflow; cat: Catalog }) {
  const qc = useQueryClient();
  const [name, setName] = useState(wf.name);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<FlowData>>(toFlow(wf.nodes, cat));
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(toFlowEdges(wf.edges));
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [issues, setIssues] = useState<Issue[]>(wf.issues);
  const [dirty, setDirty] = useState(false);
  const [input, setInput] = useState<Record<string, any>>(wf.sample_input ?? {});
  const [run, setRun] = useState<Run | null>(null);
  const [tab, setTab] = useState<"config" | "run">("config");
  const [renameTo, setRenameTo] = useState("");
  const counter = useRef(nodes.length + 1);
  const theme = document.documentElement.dataset.theme === "light" ? "light" : "dark";

  const graph = useCallback(() => ({
    name: name.trim() || "Untitled workflow", description: wf.description,
    nodes: nodes.map((n) => ({ key: n.id, type: n.data.type, config: (n.data as any).config, position: { x: Math.round(n.position.x), y: Math.round(n.position.y) } })),
    edges: edges.map((e) => ({ source: e.source, target: e.target, handle: e.sourceHandle ?? null })),
  }), [name, nodes, edges, wf.description]);

  // Debounced validation whenever the structure or config changes.
  const sig = JSON.stringify({ n: nodes.map((n) => [n.id, n.data.type, (n.data as any).config]), e: edges.map((e) => [e.source, e.target, e.sourceHandle]) });
  const firstSig = useRef(sig);
  useEffect(() => {
    if (sig === firstSig.current) return;
    setDirty(true);
    const t = setTimeout(() => {
      api.post<{ issues: Issue[] }>("/builder/validate", graph()).then((r) => setIssues(r.issues)).catch(() => {});
    }, 450);
    return () => clearTimeout(t);
  }, [sig]); // eslint-disable-line react-hooks/exhaustive-deps

  const issueByNode = useMemo(() => {
    const m: Record<string, "error" | "warning"> = {};
    issues.forEach((i) => { if (i.node && m[i.node] !== "error") m[i.node] = i.level; });
    return m;
  }, [issues]);
  const display = useMemo(() => nodes.map((n) => ({ ...n, data: { ...n.data, issue: issueByNode[n.id], status: run?.node_status?.[n.id] } })), [nodes, issueByNode, run]);

  const save = useMutation({
    mutationFn: () => api.put<Workflow>(`/builder/workflows/${wf.id}`, graph()),
    onSuccess: (w) => { setIssues(w.issues); setDirty(false); firstSig.current = sig; qc.invalidateQueries({ queryKey: ["workflows"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const start = useMutation({
    mutationFn: async () => { if (dirty) await save.mutateAsync(); return api.post<Run>(`/builder/workflows/${wf.id}/runs`, { input }); },
    onSuccess: (r) => { setRun(r); setTab("run"); },
    onError: (e) => {
      if (e instanceof ApiError && Array.isArray(e.details)) setIssues(e.details as Issue[]);
      toast.error(errorMessage(e));
    },
  });
  const decide = useMutation({
    mutationFn: ({ d, note }: { d: string; note: string }) => api.post<Run>(`/builder/runs/${run!.id}/decision`, { decision: d, note }),
    onSuccess: setRun, onError: (e) => toast.error(errorMessage(e)),
  });
  const cancel = useMutation({ mutationFn: () => api.post<Run>(`/builder/runs/${run!.id}/cancel`), onSuccess: setRun, onError: (e) => toast.error(errorMessage(e)) });

  const onConnect = useCallback((c: Connection) => {
    if (c.source === c.target) return;
    setEdges((eds) => addEdge({ ...c, id: `${c.source}-${c.sourceHandle ?? ""}-${c.target}`, style: edgeStyle(c.sourceHandle), label: c.sourceHandle ?? undefined }, eds));
  }, [setEdges]);

  const addNode = (t: NodeType) => {
    let key = t.type === "human_approval" ? "approval" : t.type;
    while (nodes.some((n) => n.id === key)) key = `${t.type === "human_approval" ? "approval" : t.type}_${counter.current++}`;
    const maxX = Math.max(0, ...nodes.map((n) => n.position.x));
    setNodes((ns) => [...ns, { id: key, type: "af", position: { x: maxX + 60, y: 260 }, data: { type: t.type, label: t.label, color: t.color, summary: summarize(t.type, t.defaults), config: structuredClone(t.defaults) } as any }]);
    setSelected(key); setTab("config");
  };
  const sel = nodes.find((n) => n.id === selected);
  const setConfig = (c: Record<string, any>) => setNodes((ns) => ns.map((n) => (n.id === selected ? { ...n, data: { ...n.data, config: c, summary: summarize(n.data.type, c) } as any } : n)));
  const removeNode = (id: string) => { setNodes((ns) => ns.filter((n) => n.id !== id)); setEdges((es) => es.filter((e) => e.source !== id && e.target !== id)); setSelected(null); };
  const rename = () => {
    const k = renameTo.trim();
    if (!/^[a-z][a-z0-9_]{0,39}$/.test(k)) return toast.error("Keys use lowercase letters, digits and underscores, starting with a letter.");
    if (nodes.some((n) => n.id === k)) return toast.error("That key is taken.");
    const old = selected!;
    setNodes((ns) => ns.map((n) => (n.id === old ? { ...n, id: k } : n)));
    setEdges((es) => es.map((e) => ({ ...e, source: e.source === old ? k : e.source, target: e.target === old ? k : e.target, id: e.id.replace(old, k) })));
    setSelected(k); setRenameTo("");
    toast.message(`Renamed. Update any {{${old}}} references in other nodes.`);
  };
  const inputFields: { name: string; label?: string; type?: string }[] = (nodes.find((n) => n.data.type === "input")?.data as any)?.config?.fields ?? [];
  const errors = issues.filter((i) => i.level === "error");

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2">
        <Link to="/builder" className="text-sm text-muted hover:text-fg">Builder</Link>
        <Input aria-label="Workflow name" value={name} onChange={(e) => { setName(e.target.value); setDirty(true); }} className="h-8 w-64" />
        <Badge tone="outline">v{wf.version}</Badge>
        {dirty && <span className="text-xs text-muted">Unsaved changes</span>}
        <span className={cn("text-xs", errors.length ? "text-fail" : "text-pass")}>{errors.length ? `${errors.length} error${errors.length > 1 ? "s" : ""}` : "Valid"}</span>
        <div className="ml-auto flex gap-2">
          <Button size="sm" variant="secondary" onClick={() => save.mutate()} disabled={save.isPending}><Save />Save</Button>
          <Button size="sm" onClick={() => start.mutate()} disabled={start.isPending || errors.length > 0}><Play />{start.isPending ? "Running…" : "Run"}</Button>
        </div>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[11rem_minmax(0,1fr)_22rem]">
        <aside className="hidden overflow-y-auto border-r border-line p-3 md:block" aria-label="Node palette">
          <p className="mb-2 text-xs text-faint">Add a node</p>
          <ul className="space-y-1">
            {cat.items.map((t) => (
              <li key={t.type}>
                <button title={t.description} onClick={() => addNode(t)} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-muted hover:bg-panel-2 hover:text-fg">
                  <span className={cn("size-2 rounded-full", DOT[t.color])} />{t.label}
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-xs text-faint">Drag from a node's right handle to another node's left handle to connect. Select an edge and press Delete to remove it. Reference earlier nodes with {"{{node_key}}"} or {"{{input.field}}"}.</p>
        </aside>
        <div className="relative min-h-[420px]">
          <ReactFlow nodes={display} edges={edges.map((e) => ({ ...e, selected: e.id === selectedEdge }))} nodeTypes={nodeTypes}
            onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
            onNodeClick={(_, n) => { setSelected(n.id); setSelectedEdge(null); setTab("config"); }} onEdgeClick={(_, e) => { setSelectedEdge(e.id); setSelected(null); }}
            onPaneClick={() => { setSelected(null); setSelectedEdge(null); }} onNodeDragStop={() => setDirty(true)}
            deleteKeyCode={["Delete", "Backspace"]} fitView fitViewOptions={{ padding: 0.2 }} onInit={(inst) => { setTimeout(() => inst.fitView({ padding: 0.2 }), 60); }} colorMode={theme} proOptions={{ hideAttribution: true }}>
            <Background gap={20} color="var(--line)" />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable className="!bg-panel" maskColor="rgba(0,0,0,0.4)" />
          </ReactFlow>
          {selectedEdge && (
            <Button size="sm" variant="secondary" className="absolute left-3 top-3 z-10" onClick={() => { setEdges((es) => es.filter((e) => e.id !== selectedEdge)); setSelectedEdge(null); }}><Trash2 />Delete connection</Button>
          )}
        </div>
        <aside className="flex min-h-0 flex-col border-l border-line">
          <div className="flex border-b border-line text-sm" role="tablist">
            {(["config", "run"] as const).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={cn("flex-1 border-b-2 px-3 py-2", tab === t ? "border-signal text-fg" : "border-transparent text-muted")}>
                {t === "config" ? "Node" : "Run"}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
            {tab === "config" && (sel ? (
              <div className="space-y-3" key={sel.id}>
                <div className="flex items-center gap-2"><span className={cn("size-2 rounded-full", DOT[sel.data.color])} /><span className="font-medium">{sel.data.label}</span><span className="font-mono text-sm text-muted">{sel.id}</span>
                  <Button size="sm" variant="ghost" className="ml-auto" aria-label="Delete node" onClick={() => removeNode(sel.id)}><Trash2 /></Button></div>
                <div className="flex gap-2"><Input aria-label="New key" value={renameTo} onChange={(e) => setRenameTo(e.target.value)} placeholder="Rename key" className="h-8" /><Button size="sm" variant="secondary" onClick={rename} disabled={!renameTo}>Rename</Button></div>
                <ConfigForm type={sel.data.type} c={(sel.data as any).config ?? {}} set={setConfig} tools={cat.tools} />
                {issues.filter((i) => i.node === sel.id).map((i, k) => <p key={k} className={cn("text-xs", i.level === "error" ? "text-fail" : "text-tool")}>{i.message}</p>)}
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-muted">Select a node to edit it.</p>
                {issues.length > 0 && (
                  <div><p className="mb-1 text-xs text-muted">Validation</p>
                    <ul className="space-y-1">{issues.map((i, k) => (
                      <li key={k}><button className={cn("text-left text-xs", i.level === "error" ? "text-fail" : "text-tool")} onClick={() => i.node && setSelected(i.node)}>{i.node && <span className="font-mono">{i.node}: </span>}{i.message}</button></li>
                    ))}</ul></div>
                )}
                <p className="text-xs text-faint">Budget per run: {cat.budget.max_steps} steps, {cat.budget.max_llm_calls} model calls, {cat.budget.max_tokens.toLocaleString()} tokens, {cat.budget.max_seconds} s.</p>
              </div>
            ))}
            {tab === "run" && (
              <div className="space-y-4">
                <div className="space-y-2">
                  {inputFields.map((f) => (
                    <div key={f.name}><Label htmlFor={`in-${f.name}`}>{f.label || f.name}</Label>
                      <Textarea id={`in-${f.name}`} rows={2} value={typeof input[f.name] === "string" ? input[f.name] : input[f.name] === undefined ? "" : JSON.stringify(input[f.name])}
                        onChange={(e) => setInput({ ...input, [f.name]: f.type === "number" ? Number(e.target.value) : e.target.value })} /></div>
                  ))}
                  <Button size="sm" onClick={() => start.mutate()} disabled={start.isPending || errors.length > 0}><Play />{start.isPending ? "Running…" : "Run with this input"}</Button>
                </div>
                {run ? <RunPanel run={run} busy={decide.isPending || cancel.isPending} onDecide={(d, note) => decide.mutate({ d, note })} onCancel={() => cancel.mutate()} /> : <p className="text-sm text-muted">Runs appear here with a step-by-step trace.</p>}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

export default function BuilderStudio() {
  const { id } = useParams();
  const cat = useQuery({ queryKey: ["builder-node-types"], queryFn: () => api.get<Catalog>("/builder/node-types"), staleTime: Infinity });
  const wf = useQuery({ queryKey: ["workflow", id], queryFn: () => api.get<Workflow>(`/builder/workflows/${id}`), refetchOnWindowFocus: false });
  if (cat.error || wf.error) return <ErrorState error={cat.error ?? wf.error} />;
  if (!cat.data || !wf.data) return <PageSkeleton />;
  return <ReactFlowProvider><Studio key={wf.data.id} wf={wf.data} cat={cat.data} /></ReactFlowProvider>;
}
