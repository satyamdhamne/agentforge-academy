import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Play, RotateCcw, Pencil } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { CodeExample } from "@/lib/types";
import { CodeBlock } from "./CodeBlock";
import { CodeEditor } from "./LazyEditor";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { cn } from "@/lib/utils";

export interface SandboxStatus {
  available: boolean;
  mode: "sandbox" | "disabled" | "unreachable";
  message: string | null;
}

export interface RunOutput {
  mode: string;
  status: string;
  stdout: string;
  stderr: string;
  exit_code: number | null;
  duration_ms: number;
  timed_out: boolean;
  truncated: boolean;
  sql?: { columns: string[]; rows: unknown[][] } | null;
  tests?: { compile_error: string | null } | null;
}

export function useSandboxStatus() {
  return useQuery({ queryKey: ["sandbox-status"], queryFn: () => api.get<SandboxStatus>("/sandbox/status"), staleTime: 60_000 });
}

export function useRunCode() {
  return useMutation({
    mutationFn: (body: { language: string; code: string; sql_setup?: string | null }) => api.post<RunOutput>("/sandbox/run", body),
  });
}

const norm = (s: string) => s.split("\n").map((l) => l.trimEnd()).join("\n").trim();

export function OutputPanel({ out, expected }: { out: RunOutput; expected?: string }) {
  const matches = expected !== undefined && out.sql == null ? norm(out.stdout) === norm(expected) : undefined;
  return (
    <div className="rounded-md border border-line bg-sunken font-mono text-[12.5px]" aria-live="polite">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-1.5 font-sans text-xs text-muted">
        <span className={cn("font-medium", out.status === "ok" ? "text-pass" : "text-fail")}>
          {out.timed_out ? "Timed out" : out.status === "ok" ? "Exited normally" : out.exit_code ? `Exited with code ${out.exit_code}` : "Error"}
        </span>
        <span className="tabular-nums">{out.duration_ms} ms</span>
        <span>Ran in the isolated sandbox</span>
        {matches !== undefined && <Badge tone={matches ? "pass" : "tool"} className="ml-auto">{matches ? "Matches expected output" : "Differs from expected output"}</Badge>}
      </div>
      {out.sql ? (
        out.tests?.compile_error ? <pre className="p-3 text-fail whitespace-pre-wrap">{out.tests.compile_error}</pre> : <SqlTable columns={out.sql.columns} rows={out.sql.rows} />
      ) : (
        <pre className="max-h-72 overflow-auto p-3 whitespace-pre-wrap scrollbar-thin">{out.stdout || <span className="text-faint">(no output)</span>}</pre>
      )}
      {out.stderr && <pre className="max-h-48 overflow-auto border-t border-line p-3 text-fail whitespace-pre-wrap scrollbar-thin">{out.stderr}</pre>}
      {out.truncated && <p className="border-t border-line px-3 py-1.5 font-sans text-xs text-faint">Output was truncated.</p>}
    </div>
  );
}

export function SqlTable({ columns, rows }: { columns: string[]; rows: unknown[][] }) {
  return (
    <div className="max-h-72 overflow-auto scrollbar-thin">
      <table className="w-full text-left">
        <thead className="sticky top-0 bg-panel-2 text-muted">
          <tr>{columns.map((c) => <th key={c} className="px-3 py-1.5 font-medium">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line">{r.map((v, j) => <td key={j} className="px-3 py-1.5">{v === null ? "NULL" : String(v)}</td>)}</tr>
          ))}
          {rows.length === 0 && <tr><td className="px-3 py-2 text-faint" colSpan={columns.length || 1}>No rows</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

/** A lesson code example: highlighted by default, editable and runnable through the sandbox when available. */
export function CodeRunner({ example }: { example: CodeExample }) {
  const { user } = useAuth();
  const status = useSandboxStatus();
  const run = useRunCode();
  const [editing, setEditing] = useState(false);
  const [code, setCode] = useState(example.code);
  const canRun = example.runnable && ["python", "javascript", "sql"].includes(example.language);
  const available = status.data?.available;

  const execute = () => run.mutate({ language: example.language, code, sql_setup: example.setup });

  return (
    <div className="space-y-2">
      {editing ? (
        <CodeEditor value={code} onChange={setCode} language={example.language} height={Math.min(420, 40 + code.split("\n").length * 20)} onRun={execute} ariaLabel={`Editor: ${example.title}`} />
      ) : (
        <CodeBlock code={code} language={example.language} />
      )}
      {canRun && (
        <div className="flex flex-wrap items-center gap-2">
          {!user ? (
            <p className="text-sm text-muted"><Link className="text-signal hover:underline" to="/login">Sign in</Link> to edit and run this example.</p>
          ) : available ? (
            <>
              <Button size="sm" onClick={execute} disabled={run.isPending}><Play />{run.isPending ? "Running…" : "Run"}</Button>
              {!editing && <Button size="sm" variant="ghost" onClick={() => setEditing(true)}><Pencil />Edit</Button>}
              {code !== example.code && <Button size="sm" variant="ghost" onClick={() => { setCode(example.code); run.reset(); }}><RotateCcw />Reset</Button>}
              <span className="text-xs text-faint">Ctrl/⌘ + Enter runs while editing</span>
            </>
          ) : (
            <p className="text-sm text-muted">{status.data?.message ?? "Checking the code runner…"} The expected output is shown below.</p>
          )}
        </div>
      )}
      {run.error && <p className="text-sm text-fail">{errorMessage(run.error)}</p>}
      {run.data ? (
        <OutputPanel out={run.data} expected={code === example.code ? example.expected_output : undefined} />
      ) : example.expected_output ? (
        <div>
          <p className="mb-1 text-xs text-faint">Expected output</p>
          <pre className="rounded-md border border-line bg-sunken p-3 font-mono text-[12.5px] whitespace-pre-wrap">{example.expected_output.trimEnd()}</pre>
        </div>
      ) : null}
    </div>
  );
}
