import { Command } from "cmdk";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import * as D from "@radix-ui/react-dialog";
import { Bot, GraduationCap, Search } from "lucide-react";
import { api } from "@/lib/api";
import type { AgentCard, Paged, TrackSummary } from "@/lib/types";
import { ADMIN_NAV, ALL_ITEMS } from "./nav";
import { useAuth } from "@/lib/auth";

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const nav = useNavigate();
  const { isStaff } = useAuth();
  const tracks = useQuery({ queryKey: ["tracks"], queryFn: () => api.get<{ items: TrackSummary[] }>("/tracks"), enabled: open });
  const agents = useQuery({ queryKey: ["agents", {}], queryFn: () => api.get<Paged<AgentCard>>("/agents"), enabled: open });
  const go = (to: string) => { onOpenChange(false); nav(to); };
  const item = "flex cursor-pointer items-center gap-2.5 rounded px-2.5 py-2 text-sm text-muted aria-selected:bg-panel-2 aria-selected:text-fg";
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-black/50" />
        <D.Content className="fixed left-1/2 top-[14vh] z-50 w-[min(92vw,600px)] -translate-x-1/2 overflow-hidden rounded-lg border border-line bg-panel shadow-2xl" aria-describedby={undefined}>
          <D.Title className="sr-only">Search</D.Title>
          <Command label="Search the academy" loop>
            <div className="flex items-center gap-2 border-b border-line px-3">
              <Search className="size-4 text-faint" />
              <Command.Input autoFocus placeholder="Jump to a page, path or agent…" className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-faint" />
            </div>
            <Command.List className="max-h-[60vh] overflow-y-auto p-1.5 scrollbar-thin">
              <Command.Empty className="px-3 py-6 text-center text-sm text-muted">No matches.</Command.Empty>
              <Command.Group heading="Pages" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:text-faint">
                {[...ALL_ITEMS, ...(isStaff ? [ADMIN_NAV] : [])].map((i) => (
                  <Command.Item key={i.to} value={i.label} onSelect={() => go(i.to)} className={item}>
                    <i.icon className="size-4" /> {i.label}
                    {i.planned && <span className="ml-auto text-xs text-faint">{i.planned.phase}</span>}
                  </Command.Item>
                ))}
              </Command.Group>
              <Command.Group heading="Learning paths" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:text-faint">
                {tracks.data?.items.map((t) => (
                  <Command.Item key={t.slug} value={`path ${t.title}`} onSelect={() => go(`/paths/${t.slug}`)} className={item}>
                    <GraduationCap className="size-4" /> {t.title}
                  </Command.Item>
                ))}
              </Command.Group>
              <Command.Group heading="Agents" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:text-faint">
                {agents.data?.items.map((a) => (
                  <Command.Item key={a.slug} value={`agent ${a.name} ${a.category}`} onSelect={() => go(`/agents/${a.slug}`)} className={item}>
                    <Bot className="size-4" /> {a.name}
                    {a.has_reference_impl && <span className="ml-auto text-xs text-pass">Runnable</span>}
                  </Command.Item>
                ))}
              </Command.Group>
            </Command.List>
          </Command>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

export function useCommandShortcut(setOpen: (fn: (v: boolean) => boolean) => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);
}

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useCommandShortcut(setOpen);
  return { open, setOpen };
}
