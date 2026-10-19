import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({ title, description, children, className }: { title: string; description?: string; children: ReactNode; className?: string }) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px]" />
      <D.Content className={cn("fixed left-1/2 top-[12vh] z-50 w-[min(92vw,560px)] -translate-x-1/2 rounded-lg border border-line bg-panel p-5 shadow-2xl", className)}>
        <D.Title className="font-display text-lg font-semibold">{title}</D.Title>
        {description && <D.Description className="mt-1 text-sm text-muted">{description}</D.Description>}
        <div className="mt-4">{children}</div>
        <D.Close className="absolute right-3 top-3 rounded p-1 text-muted hover:text-fg" aria-label="Close">
          <X className="size-4" />
        </D.Close>
      </D.Content>
    </D.Portal>
  );
}
