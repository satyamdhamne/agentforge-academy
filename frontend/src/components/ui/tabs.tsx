import * as T from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

export const Tabs = T.Root;

export function TabsList({ className, ...p }: T.TabsListProps) {
  return <T.List className={cn("flex gap-1 overflow-x-auto border-b border-line scrollbar-thin", className)} {...p} />;
}

export function TabsTrigger({ className, ...p }: T.TabsTriggerProps) {
  return (
    <T.Trigger
      className={cn(
        "-mb-px whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-sm text-muted transition-colors hover:text-fg data-[state=active]:border-signal data-[state=active]:text-fg",
        className,
      )}
      {...p}
    />
  );
}

export function TabsContent({ className, ...p }: T.TabsContentProps) {
  return <T.Content className={cn("pt-6 focus-visible:outline-none", className)} {...p} />;
}
