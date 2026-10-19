import type { HTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badge = cva("inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium leading-none whitespace-nowrap", {
  variants: {
    tone: {
      neutral: "bg-panel-2 text-muted border border-line",
      signal: "bg-signal/12 text-signal",
      llm: "bg-llm/12 text-llm",
      tool: "bg-tool/14 text-tool",
      pass: "bg-pass/12 text-pass",
      fail: "bg-fail/12 text-fail",
      outline: "border border-line-strong text-muted",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export function Badge({ className, tone, ...p }: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badge>) {
  return <span className={cn(badge({ tone }), className)} {...p} />;
}
