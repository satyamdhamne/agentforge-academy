import { useState } from "react";
import { Link } from "react-router-dom";
import { Play, ShieldCheck, ShieldOff } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CodeEditor } from "@/components/LazyEditor";
import { OutputPanel, useRunCode, useSandboxStatus } from "@/components/CodeRunner";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/States";

const STARTERS: Record<string, { label: string; code: string; setup?: string }> = {
  python: {
    label: "Python",
    code: `from collections import Counter

def top_words(text, n=3):
    words = [w.strip(".,!?").lower() for w in text.split()]
    return Counter(w for w in words if w).most_common(n)

print(top_words("The agent called the tool, the tool returned, the agent answered."))
`,
  },
  javascript: {
    label: "JavaScript",
    code: `// Microtasks run before timers - predict the order, then run it.
setTimeout(() => console.log("timer"), 0);
Promise.resolve().then(() => console.log("microtask"));
console.log("sync");
`,
  },
  sql: {
    label: "SQL",
    setup: `CREATE TABLE runs (id INTEGER PRIMARY KEY, agent TEXT, status TEXT, tokens INTEGER);
INSERT INTO runs (agent, status, tokens) VALUES
  ('pr-review', 'succeeded', 1200), ('pr-review', 'failed', 300),
  ('sql-assistant', 'succeeded', 900), ('sql-assistant', 'succeeded', 1100),
  ('log-analysis', 'succeeded', 2400);`,
    code: `SELECT agent,
       COUNT(*) AS runs,
       ROUND(AVG(tokens)) AS avg_tokens,
       SUM(status = 'succeeded') * 1.0 / COUNT(*) AS success_rate
FROM runs
GROUP BY agent
ORDER BY runs DESC, agent;
`,
  },
};

export default function CodeLab() {
  const { user } = useAuth();
  const status = useSandboxStatus();
  const run = useRunCode();
  const [lang, setLang] = useState<keyof typeof STARTERS>("python");
  const [code, setCode] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(STARTERS).map(([k, v]) => [k, v.code])));
  const [setup, setSetup] = useState(STARTERS.sql.setup!);
  const available = !!status.data?.available;
  const execute = () => run.mutate({ language: lang, code: code[lang], sql_setup: lang === "sql" ? setup : undefined });

  return (
    <div>
      <PageHeader title="Interactive Coding Lab" description="Write Python, JavaScript or SQL and run it in an isolated sandbox: separate container, no network, read-only filesystem, and strict CPU, memory, process and time limits." />
      <div className={cn("mb-5 flex items-start gap-3 rounded-lg border px-4 py-3 text-sm", available ? "border-pass/30 bg-pass/5" : "border-tool/40 bg-tool/5")}>
        {available ? <ShieldCheck className="mt-0.5 size-4 shrink-0 text-pass" /> : <ShieldOff className="mt-0.5 size-4 shrink-0 text-tool" />}
        <p>{available ? "Connected to the sandbox runner. Your code never runs in the web server or in your browser." : (status.data?.message ?? "Checking the code runner…") + " You can still edit code here."}</p>
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2" role="tablist" aria-label="Language">
        {Object.entries(STARTERS).map(([k, v]) => (
          <button key={k} role="tab" aria-selected={lang === k} onClick={() => { setLang(k as keyof typeof STARTERS); run.reset(); }}
            className={cn("rounded-md px-3 py-1.5 text-sm", lang === k ? "bg-panel-2 text-fg" : "text-muted hover:text-fg")}>{v.label}</button>
        ))}
        <div className="ml-auto flex items-center gap-3">
          <span className="hidden text-xs text-faint sm:inline">Ctrl/⌘ + Enter</span>
          {user ? (
            <Button onClick={execute} disabled={!available || run.isPending}><Play />{run.isPending ? "Running…" : "Run"}</Button>
          ) : (
            <Button asChild><Link to="/login?next=/lab">Sign in to run code</Link></Button>
          )}
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          {lang === "sql" && (
            <details open className="rounded-md border border-line p-2">
              <summary className="cursor-pointer px-1 text-sm text-muted">Schema and seed data (SQLite, runs before your query)</summary>
              <div className="mt-2"><CodeEditor value={setup} onChange={setSetup} language="sql" height={150} ariaLabel="SQL setup" /></div>
            </details>
          )}
          <CodeEditor key={lang} value={code[lang]} onChange={(v) => setCode({ ...code, [lang]: v })} language={lang} height={lang === "sql" ? 300 : 460} onRun={() => user && available && execute()} ariaLabel={`${STARTERS[lang].label} editor`} />
        </div>
        <div>
          {run.error && <p className="mb-3 text-sm text-fail">{errorMessage(run.error)}</p>}
          {run.data ? <OutputPanel out={run.data} /> : (
            <div className="grid h-full min-h-48 place-items-center rounded-md border border-dashed border-line-strong p-6 text-center text-sm text-muted">
              Output appears here. Each run gets a fresh process and a 5-second limit.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
