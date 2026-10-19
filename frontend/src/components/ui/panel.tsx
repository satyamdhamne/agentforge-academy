import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/** A bordered surface. Used sparingly - most content sits directly on the page. */
export function Panel({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-lg border border-line bg-panel", className)} {...p} />;
}
