import { Lock } from "lucide-react";
import { Badge } from "./ui/badge";
import { LEVEL_LABEL } from "@/lib/utils";

const LEVEL_DOTS: Record<string, number> = { beginner: 1, intermediate: 2, advanced: 3, expert: 4 };

/** Difficulty shown as filled pips, so level reads at a glance without colour alone. */
export function LevelPips({ level }: { level: string }) {
  const n = LEVEL_DOTS[level] ?? 1;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted" title={LEVEL_LABEL[level]}>
      <span className="inline-flex gap-[3px]" aria-hidden>
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className={`h-2.5 w-1 rounded-sm ${i <= n ? "bg-signal" : "bg-line-strong"}`} />
        ))}
      </span>
      {LEVEL_LABEL[level] ?? level}
    </span>
  );
}

export function TierBadge({ tier, locked }: { tier: string; locked?: boolean }) {
  if (tier === "free" && !locked) return null;
  return (
    <Badge tone={locked ? "tool" : "outline"}>
      {locked && <Lock className="size-3" />}
      {tier === "pro" ? "Pro" : tier === "team" ? "Team" : "Free"}
    </Badge>
  );
}
