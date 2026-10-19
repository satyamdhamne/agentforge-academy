import { useQuery } from "@tanstack/react-query";
import { Check, Minus } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, titleCase } from "@/lib/utils";
import { PageHeader } from "@/components/States";

interface Plan { key: string; name: string; price_hint: string; tagline: string; highlights: string[]; features: Record<string, number | boolean | null> }

export default function Pricing() {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["plans"], queryFn: () => api.get<{ items: Plan[]; payments_enabled: boolean }>("/plans") });
  const keys = q.data ? Object.keys(q.data.items[0]?.features ?? {}) : [];
  const show = (v: number | boolean | null) => (v === true ? <Check className="size-4 text-pass" aria-label="Included" /> : v === false ? <Minus className="size-4 text-faint" aria-label="Not included" /> : v === null ? "Unlimited" : `${v} / day`);
  return (
    <div>
      <PageHeader title="Plans" description="Plans are configuration, not code: limits live in the entitlements table and an admin can assign plans today. Online payments aren’t enabled yet." />
      <div className="grid gap-4 md:grid-cols-3">
        {q.data?.items.map((p) => (
          <div key={p.key} className={cn("rounded-lg border p-5", p.key === "pro" ? "border-signal/60" : "border-line")}>
            <div className="flex items-baseline justify-between"><h2 className="font-display text-xl font-semibold">{p.name}</h2><span className="text-sm text-muted">{p.price_hint}</span></div>
            <p className="mt-1 text-sm text-muted">{p.tagline}</p>
            {user?.plan === p.key && <p className="mt-3 text-sm text-pass">Your current plan</p>}
            <ul className="mt-4 space-y-1.5 text-sm">{p.highlights.map((h) => <li key={h} className="flex gap-2"><Check className="mt-0.5 size-4 shrink-0 text-pass" />{h}</li>)}</ul>
          </div>
        ))}
      </div>
      {keys.length > 0 && (
        <div className="mt-10 overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-sm">
            <thead className="bg-panel-2 text-left text-muted"><tr><th className="px-4 py-2 font-medium">Feature</th>{q.data!.items.map((p) => <th key={p.key} className="px-4 py-2 font-medium">{p.name}</th>)}</tr></thead>
            <tbody>{keys.map((k) => <tr key={k} className="border-t border-line"><td className="px-4 py-2">{titleCase(k)}</td>{q.data!.items.map((p) => <td key={p.key} className="px-4 py-2">{show(p.features[k])}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
