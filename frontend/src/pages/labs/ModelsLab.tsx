import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Input, Label, Select } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorState, PageHeader } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Metric } from "@/components/LabBits";
import { CodeBlock } from "@/components/CodeBlock";

interface Model { key: string; name: string; family: string; params_b: number | null; context_k: number; license: string; open_weights: boolean;
  class: "slm" | "llm" | "api"; strengths: string[]; weaknesses: string[] }
interface Technique { key: string; name: string; summary: string; when: string; watch_out: string }
interface Catalog { version_note: string; models: Model[]; techniques: Technique[] }
interface Providers { server_provider: string; server_model: string; local_model: boolean; your_plan: string; you_get: string; how_to_run_locally: string }

const BITS: Record<string, number> = { "16-bit (FP16/BF16)": 16, "8-bit (INT8)": 8, "4-bit (Q4/AWQ/GPTQ)": 4.5 };
const gb = (v: number) => (v < 10 ? v.toFixed(1) : Math.round(v).toString());

/** Rough KV-cache size per token for grouped-query-attention models, fitted to Llama 3.1 8B (~0.125 MB) and 70B (~0.31 MB). */
function kvMbPerToken(paramsB: number) {
  return 0.04 * Math.pow(paramsB, 0.48);
}

export function estimateMemory(paramsB: number, bits: number, contextTokens: number, batch: number) {
  const weights = (paramsB * bits) / 8;
  const kv = (kvMbPerToken(paramsB) * contextTokens * batch) / 1024;
  const overhead = Math.max(0.5, 0.08 * (weights + kv));
  return { weights, kv, overhead, total: weights + kv + overhead, lora: paramsB * 2 * 1.25 + 2, qlora: paramsB * 0.56 * 1.3 + 2, full: paramsB * 16 };
}

function MemoryCalc({ models }: { models: Model[] }) {
  const open = models.filter((m) => m.params_b);
  const [paramsB, setParamsB] = useState(8);
  const [bitsKey, setBitsKey] = useState("4-bit (Q4/AWQ/GPTQ)");
  const [ctx, setCtx] = useState(8192);
  const [batch, setBatch] = useState(1);
  const m = estimateMemory(paramsB, BITS[bitsKey], ctx, batch);
  const fits = m.total <= 8 ? "an 8 GB laptop GPU or Apple silicon with 16 GB" : m.total <= 16 ? "a 16 GB GPU" : m.total <= 24 ? "a 24 GB GPU (RTX 4090 / L4)" : m.total <= 48 ? "a 48 GB GPU (L40S / A6000)" : m.total <= 80 ? "one 80 GB GPU (A100 / H100)" : `${Math.ceil(m.total / 80)} x 80 GB GPUs with tensor parallelism`;
  return (
    <div className="grid gap-8 lg:grid-cols-[18rem_minmax(0,1fr)]">
      <div className="space-y-4">
        <div><Label htmlFor="preset">Model</Label>
          <Select id="preset" value={String(paramsB)} onChange={(e) => setParamsB(Number(e.target.value))}>
            {open.map((x) => <option key={x.key} value={x.params_b!}>{x.name} ({x.params_b}B)</option>)}
            {!open.some((x) => x.params_b === paramsB) && <option value={paramsB}>Custom ({paramsB}B)</option>}
          </Select></div>
        <div><Label htmlFor="params">Parameters (billions)</Label><Input id="params" type="number" min={0.1} max={1000} step={0.1} value={paramsB} onChange={(e) => setParamsB(Math.max(0.1, Number(e.target.value)))} /></div>
        <div><Label htmlFor="bits">Weight precision</Label>
          <Select id="bits" value={bitsKey} onChange={(e) => setBitsKey(e.target.value)}>{Object.keys(BITS).map((k) => <option key={k}>{k}</option>)}</Select></div>
        <div><Label htmlFor="ctx">Context length (tokens)</Label><Input id="ctx" type="number" min={256} max={1_000_000} step={256} value={ctx} onChange={(e) => setCtx(Number(e.target.value))} /></div>
        <div><Label htmlFor="batch">Concurrent sequences</Label><Input id="batch" type="number" min={1} max={256} value={batch} onChange={(e) => setBatch(Math.max(1, Number(e.target.value)))} /></div>
      </div>
      <div className="space-y-6">
        <dl className="grid grid-cols-2 gap-4 rounded-lg border border-line p-4 sm:grid-cols-4">
          <Metric label="Weights" value={`${gb(m.weights)} GB`} />
          <Metric label="KV cache" value={`${gb(m.kv)} GB`} hint="Grows with context length x concurrent sequences" />
          <Metric label="Runtime overhead" value={`${gb(m.overhead)} GB`} />
          <Metric label="Inference total" value={`${gb(m.total)} GB`} />
        </dl>
        <div className="h-3 overflow-hidden rounded-full bg-panel-2" aria-hidden>
          <div className="flex h-full">
            <span className="bg-signal" style={{ width: `${(m.weights / m.total) * 100}%` }} />
            <span className="bg-llm" style={{ width: `${(m.kv / m.total) * 100}%` }} />
            <span className="bg-tool" style={{ width: `${(m.overhead / m.total) * 100}%` }} />
          </div>
        </div>
        <p>Fits on {fits}.</p>
        <div>
          <h3 className="mb-2 font-display text-base font-semibold">Fine-tuning memory (approximate)</h3>
          <dl className="grid grid-cols-3 gap-4 rounded-lg border border-line p-4">
            <Metric label="QLoRA (4-bit base)" value={`${gb(m.qlora)} GB`} />
            <Metric label="LoRA (16-bit base)" value={`${gb(m.lora)} GB`} />
            <Metric label="Full fine-tune (Adam)" value={`${gb(m.full)} GB`} hint="About 16 bytes per parameter for weights, gradients and optimizer state" />
          </dl>
        </div>
        <p className="text-xs text-faint">Back-of-envelope estimates for planning, not guarantees. Real usage depends on the architecture (layers, KV heads), the runtime (vLLM, llama.cpp, TGI), and settings like paged attention. Always confirm with a real load test.</p>
      </div>
    </div>
  );
}

function CostCalc() {
  const [reqs, setReqs] = useState(20000);
  const [inTok, setInTok] = useState(1200);
  const [outTok, setOutTok] = useState(250);
  const [inPrice, setInPrice] = useState(0.15);
  const [outPrice, setOutPrice] = useState(0.6);
  const [gpuHr, setGpuHr] = useState(1.2);
  const [gpus, setGpus] = useState(1);
  const [tps, setTps] = useState(1500);
  const monthReq = reqs * 30;
  const api$ = (monthReq * (inTok * inPrice + outTok * outPrice)) / 1e6;
  const self$ = gpuHr * gpus * 24 * 30;
  const neededTps = (reqs * outTok) / 86400;
  const peakTps = neededTps * 3;
  const util = Math.min(1, peakTps / (tps * gpus));
  const field = (id: string, label: string, v: number, set: (n: number) => void, step = 1) => (
    <div><Label htmlFor={id}>{label}</Label><Input id={id} type="number" min={0} step={step} value={v} onChange={(e) => set(Number(e.target.value))} /></div>
  );
  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-3">
        <fieldset className="space-y-3"><legend className="mb-2 text-sm font-medium">Workload</legend>
          {field("reqs", "Requests per day", reqs, setReqs, 100)}{field("in", "Input tokens per request", inTok, setInTok, 50)}{field("out", "Output tokens per request", outTok, setOutTok, 10)}</fieldset>
        <fieldset className="space-y-3"><legend className="mb-2 text-sm font-medium">Hosted API</legend>
          {field("pin", "$ per 1M input tokens", inPrice, setInPrice, 0.01)}{field("pout", "$ per 1M output tokens", outPrice, setOutPrice, 0.01)}</fieldset>
        <fieldset className="space-y-3"><legend className="mb-2 text-sm font-medium">Self-hosted</legend>
          {field("gpuhr", "$ per GPU hour", gpuHr, setGpuHr, 0.1)}{field("gpus", "GPUs (always on)", gpus, setGpus)}{field("tps", "Output tokens/s per GPU (batched)", tps, setTps, 100)}</fieldset>
      </div>
      <dl className="grid grid-cols-2 gap-4 rounded-lg border border-line p-4 sm:grid-cols-4">
        <Metric label="Hosted API per month" value={`$${Math.round(api$).toLocaleString()}`} />
        <Metric label="Self-hosted per month" value={`$${Math.round(self$).toLocaleString()}`} />
        <Metric label="Peak GPU utilisation" value={`${Math.round(util * 100)}%`} hint="Assumes peak traffic is 3x the daily average" />
        <Metric label="Cheaper option" value={api$ <= self$ ? "Hosted API" : "Self-hosted"} />
      </dl>
      {util >= 1 && <p className="text-sm text-fail">The self-hosted setup can't keep up with peak traffic. Add GPUs or a smaller model.</p>}
      <p className="text-sm text-muted">Break-even is around {Math.round((self$ / Math.max(api$, 0.0001)) * reqs).toLocaleString()} requests per day at these prices. Self-hosting also costs engineering time for serving, scaling, monitoring and upgrades, which this doesn't count.</p>
    </div>
  );
}

const TASKS = { simple: "Classification, extraction, routing", general: "Chat, summarisation, drafting", hard: "Multi-step reasoning, code, agents" } as const;

function Selector({ models }: { models: Model[] }) {
  const [task, setTask] = useState<keyof typeof TASKS>("general");
  const [privateData, setPrivate] = useState(false);
  const [hardware, setHardware] = useState("24");
  const [longCtx, setLongCtx] = useState(false);
  const ranked = useMemo(() => {
    const vram = { cpu: 8, "24": 24, "80": 80, none: 0 }[hardware] ?? 0;
    return models.map((m) => {
      let score = 0;
      const why: string[] = [];
      const fitsGb = m.params_b ? estimateMemory(m.params_b, 4.5, 8192, 1).total : Infinity;
      if (privateData && !m.open_weights) { score -= 100; why.push("Data must stay in your environment, and this is hosted only"); }
      if (m.open_weights && hardware !== "none" && fitsGb > vram) { score -= 50; why.push(`Needs about ${gb(fitsGb)} GB at 4-bit; you have ${vram} GB`); }
      if (m.open_weights && hardware === "none") { score -= 15; why.push("Needs hardware or a hosting provider"); }
      if (longCtx && m.context_k < 100) { score -= 30; why.push(`Only ${m.context_k}k context`); }
      if (task === "simple") { score += m.class === "slm" ? 30 : m.class === "api" && m.key === "api-small" ? 20 : 0; if (m.class === "slm") why.push("Small models handle narrow tasks well and are cheap to fine-tune"); }
      if (task === "general") { score += m.class === "slm" ? 15 : 20; }
      if (task === "hard") { score += m.key === "api-frontier" ? 40 : m.class === "llm" ? 25 : m.key === "api-small" ? 10 : 0; if (m.class === "slm") why.push("Small models struggle with long multi-step reasoning"); }
      if (m.key === "api-frontier" && task !== "hard") { score -= 10; why.push("More capability and cost than this task needs"); }
      return { m, score, why };
    }).sort((a, b) => b.score - a.score);
  }, [models, task, privateData, hardware, longCtx]);
  return (
    <div className="grid gap-8 lg:grid-cols-[18rem_minmax(0,1fr)]">
      <div className="space-y-4">
        <div><Label htmlFor="task">Task</Label><Select id="task" value={task} onChange={(e) => setTask(e.target.value as keyof typeof TASKS)}>
          {Object.entries(TASKS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></div>
        <div><Label htmlFor="hw">Hardware you can use</Label><Select id="hw" value={hardware} onChange={(e) => setHardware(e.target.value)}>
          <option value="none">None: hosted APIs only</option><option value="cpu">CPU or laptop (about 8 GB)</option><option value="24">One 24 GB GPU</option><option value="80">One 80 GB GPU</option></Select></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-[var(--signal)]" checked={privateData} onChange={(e) => setPrivate(e.target.checked)} />Data can't leave our environment</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-[var(--signal)]" checked={longCtx} onChange={(e) => setLongCtx(e.target.checked)} />Needs 100k+ token context</label>
      </div>
      <ol className="space-y-3">
        {ranked.slice(0, 5).map(({ m, score, why }, i) => (
          <li key={m.key} className="rounded-lg border border-line p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm text-faint">{i + 1}</span><span className="font-medium">{m.name}</span>
              <Badge tone={m.class === "api" ? "llm" : m.class === "slm" ? "pass" : "signal"}>{m.class.toUpperCase()}</Badge>
              {score < 0 && <Badge tone="fail">Poor fit</Badge>}
            </div>
            <p className="mt-1 text-sm text-muted">{m.strengths.join("; ")}</p>
            {why.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm">{why.map((w) => <li key={w}>{w}</li>)}</ul>}
          </li>
        ))}
      </ol>
    </div>
  );
}

export default function ModelsLab() {
  const cat = useQuery({ queryKey: ["llm-catalog"], queryFn: () => api.get<Catalog>("/llm-lab/catalog") });
  const prov = useQuery({ queryKey: ["llm-providers"], queryFn: () => api.get<Providers>("/llm-lab/providers") });
  if (cat.error) return <ErrorState error={cat.error} />;
  if (!cat.data) return <PageSkeleton />;
  return (
    <div>
      <PageHeader title="LLM & SLM Lab" description="Pick the smallest model that does the job. Estimate memory and cost, compare open and hosted models, and learn when quantization, LoRA or distillation pay off." />
      <Tabs defaultValue="select">
        <TabsList>
          <TabsTrigger value="select">Model selector</TabsTrigger>
          <TabsTrigger value="memory">Memory calculator</TabsTrigger>
          <TabsTrigger value="cost">Cost calculator</TabsTrigger>
          <TabsTrigger value="catalog">Catalog</TabsTrigger>
          <TabsTrigger value="techniques">Techniques</TabsTrigger>
          <TabsTrigger value="local">Run locally</TabsTrigger>
        </TabsList>
        <TabsContent value="select"><Selector models={cat.data.models} /></TabsContent>
        <TabsContent value="memory"><MemoryCalc models={cat.data.models} /></TabsContent>
        <TabsContent value="cost"><CostCalc /></TabsContent>
        <TabsContent value="catalog">
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-sm">
              <thead className="bg-panel-2 text-left text-muted"><tr><th className="px-3 py-2 font-medium">Model</th><th className="px-3 py-2 font-medium">Size</th><th className="px-3 py-2 font-medium">Context</th><th className="px-3 py-2 font-medium">License</th><th className="px-3 py-2 font-medium">Strengths</th><th className="px-3 py-2 font-medium">Weaknesses</th></tr></thead>
              <tbody>{cat.data.models.map((m) => (
                <tr key={m.key} className="border-t border-line align-top">
                  <td className="px-3 py-2"><span className="font-medium">{m.name}</span><span className="block text-xs text-muted">{m.family}</span></td>
                  <td className="px-3 py-2 tabular-nums">{m.params_b ? `${m.params_b}B` : "Not disclosed"}</td>
                  <td className="px-3 py-2 tabular-nums">{m.context_k}k</td>
                  <td className="px-3 py-2">{m.license}{m.open_weights && <Badge tone="pass" className="ml-1">open weights</Badge>}</td>
                  <td className="px-3 py-2 text-muted">{m.strengths.join("; ")}</td>
                  <td className="px-3 py-2 text-muted">{m.weaknesses.join("; ")}</td>
                </tr>))}</tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-faint">{cat.data.version_note}</p>
        </TabsContent>
        <TabsContent value="techniques">
          <div className="grid gap-4 md:grid-cols-2">
            {cat.data.techniques.map((t) => (
              <article key={t.key} className="rounded-lg border border-line p-4">
                <h3 className="font-display text-lg font-semibold">{t.name}</h3>
                <p className="mt-1 text-sm">{t.summary}</p>
                <p className="mt-3 text-sm"><span className="text-pass">Use when:</span> {t.when}</p>
                <p className="mt-1 text-sm"><span className="text-tool">Watch out:</span> {t.watch_out}</p>
              </article>
            ))}
          </div>
        </TabsContent>
        <TabsContent value="local">
          {prov.data ? (
            <div className="max-w-3xl space-y-4">
              <dl className="grid grid-cols-2 gap-4 rounded-lg border border-line p-4 sm:grid-cols-3">
                <Metric label="Server provider" value={prov.data.server_provider} />
                <Metric label="Server model" value={<span className="text-base">{prov.data.server_model}</span>} />
                <Metric label="You get" value={prov.data.you_get === "live" ? "Live model" : "Simulator"} />
              </dl>
              {prov.data.local_model && <p className="text-sm text-pass">This server is already using a local model.</p>}
              <p className="text-sm text-muted">Any OpenAI-compatible server works, including Ollama, vLLM, LM Studio and llama.cpp. To point AgentForge at a local model:</p>
              <CodeBlock code={`ollama pull llama3.1:8b\n\n# .env\nLLM_PROVIDER=openai\nOPENAI_BASE_URL=http://host.docker.internal:11434/v1\nOPENAI_MODEL=llama3.1:8b\nOPENAI_API_KEY=ollama`} language="bash" />
              <p className="text-sm text-muted">Then restart with <code className="font-mono">docker compose up -d backend</code>. Learners on paid plans get the live model; Free stays on the simulator.</p>
            </div>
          ) : prov.error ? <ErrorState error={prov.error} /> : <PageSkeleton />}
        </TabsContent>
      </Tabs>
    </div>
  );
}
