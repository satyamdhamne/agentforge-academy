import { useNavigate, Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { formatDate, pluralize } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorState, PageHeader } from "@/components/States";
import { PageSkeleton } from "@/components/ui/skeleton";

interface Wf { id: string; name: string; description: string; version: number; status: string; updated_at: string; nodes: number }
interface Tpl { slug: string; name: string; description: string; nodes: number }

export default function BuilderHome() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const wfs = useQuery({ queryKey: ["workflows"], queryFn: () => api.get<{ items: Wf[] }>("/builder/workflows") });
  const tpls = useQuery({ queryKey: ["builder-templates"], queryFn: () => api.get<{ items: Tpl[] }>("/builder/templates") });
  const create = useMutation({
    mutationFn: (template?: string) => api.post<{ id: string }>("/builder/workflows", { template: template ?? null }),
    onSuccess: (w) => { qc.invalidateQueries({ queryKey: ["workflows"] }); nav(`/builder/${w.id}`); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: (id: string) => api.delete(`/builder/workflows/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (wfs.error) return <ErrorState error={wfs.error} />;
  return (
    <div className="space-y-10">
      <PageHeader title="Agent Builder Studio" description="Wire inputs, prompts, model calls, retrieval, tools, conditions and human approvals into a workflow. Validate it, run it, and inspect every step."
        actions={<Button onClick={() => create.mutate(undefined)} disabled={create.isPending}><Plus />Blank workflow</Button>} />
      <section>
        <h2 className="mb-3 font-display text-lg font-semibold">Start from a template</h2>
        {tpls.isLoading ? <PageSkeleton /> : (
          <ul className="grid gap-3 md:grid-cols-2">
            {tpls.data?.items.map((t) => (
              <li key={t.slug}>
                <button onClick={() => create.mutate(t.slug)} disabled={create.isPending} className="h-full w-full rounded-lg border border-line p-4 text-left transition-colors hover:border-line-strong hover:bg-panel">
                  <span className="font-medium">{t.name}</span>
                  <span className="mt-1 block text-sm text-muted">{t.description}</span>
                  <span className="mt-2 block text-xs text-faint">{pluralize(t.nodes, "node")}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <h2 className="mb-3 font-display text-lg font-semibold">Your workflows</h2>
        {wfs.isLoading ? <PageSkeleton /> : !wfs.data?.items.length ? (
          <p className="text-sm text-muted">None yet. Templates are the quickest way in: each one shows a pattern worth knowing.</p>
        ) : (
          <ul className="divide-y divide-line rounded-lg border border-line">
            {wfs.data.items.map((w) => (
              <li key={w.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <Link to={`/builder/${w.id}`} className="min-w-0 flex-1 font-medium hover:text-signal">{w.name}</Link>
                <Badge tone="outline">v{w.version}</Badge>
                <span className="text-xs text-muted">{pluralize(w.nodes, "node")}</span>
                <span className="w-28 text-right text-xs text-muted">{formatDate(w.updated_at)}</span>
                <Button size="sm" variant="ghost" aria-label={`Delete ${w.name}`} onClick={() => { if (window.confirm(`Delete "${w.name}" and its runs?`)) del.mutate(w.id); }}><Trash2 /></Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
