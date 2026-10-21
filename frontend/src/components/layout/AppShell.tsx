import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ErrorBoundary } from "../ErrorBoundary";
import * as D from "@radix-ui/react-dialog";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { LogOut, Menu as MenuIcon, Moon, Search, Settings, Sun, User as UserIcon } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { Button } from "../ui/button";
import { ADMIN_NAV, NAV, type NavItem } from "./nav";
import { CommandPalette, useCommandPalette } from "./CommandPalette";
import { Logo } from "./Logo";

function NavEntry({ item, onNavigate }: { item: NavItem; onNavigate?: () => void }) {
  return (
    <NavLink
      to={item.to}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          "group flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13.5px] transition-colors",
          isActive ? "bg-panel-2 text-fg" : "text-muted hover:bg-panel-2/60 hover:text-fg",
          item.planned && "text-faint",
        )
      }
    >
      <item.icon className="size-4 shrink-0" />
      <span className="truncate">{item.label}</span>
      {item.planned && <span className="ml-auto text-[11px] text-faint">Soon</span>}
    </NavLink>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, isStaff } = useAuth();
  return (
    <nav aria-label="Main" className="flex h-full flex-col gap-5 overflow-y-auto px-3 pb-6 scrollbar-thin">
      {NAV.map((g) => (
        <div key={g.group}>
          <p className="mb-1 px-2.5 text-xs font-medium text-faint">{g.group}</p>
          <div className="space-y-0.5">
            {g.items.filter((i) => !i.auth || user).map((i) => <NavEntry key={i.to} item={i} onNavigate={onNavigate} />)}
          </div>
        </div>
      ))}
      {isStaff && (
        <div>
          <p className="mb-1 px-2.5 text-xs font-medium text-faint">Manage</p>
          <NavEntry item={ADMIN_NAV} onNavigate={onNavigate} />
        </div>
      )}
    </nav>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  if (!user) {
    return (
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => nav("/login")}>Sign in</Button>
        <Button size="sm" className="hidden sm:inline-flex" onClick={() => nav("/register")}>Create account</Button>
      </div>
    );
  }
  const initials = user.profile.display_name.split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  return (
    <Menu.Root>
      <Menu.Trigger className="flex items-center gap-2 rounded-full p-0.5 pr-2 hover:bg-panel-2" aria-label="Account menu">
        <span className="grid size-7 place-items-center rounded-full bg-signal/15 text-xs font-semibold text-signal">{initials}</span>
        <span className="hidden text-sm sm:inline">{user.profile.display_name}</span>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content align="end" sideOffset={6} className="z-50 min-w-52 rounded-md border border-line bg-panel p-1 shadow-xl">
          <div className="px-2.5 py-2 text-xs text-muted">
            {user.email}
            <span className="mt-0.5 block capitalize text-faint">{user.plan} plan</span>
          </div>
          <Menu.Separator className="my-1 h-px bg-line" />
          {[
            { label: "Profile & settings", icon: Settings, to: "/settings" },
            { label: "Progress & achievements", icon: UserIcon, to: "/progress" },
          ].map((i) => (
            <Menu.Item key={i.to} onSelect={() => nav(i.to)} className="flex cursor-pointer items-center gap-2 rounded px-2.5 py-1.5 text-sm outline-none data-[highlighted]:bg-panel-2">
              <i.icon className="size-4 text-muted" /> {i.label}
            </Menu.Item>
          ))}
          <Menu.Item onSelect={async () => { await logout(); nav("/"); }} className="flex cursor-pointer items-center gap-2 rounded px-2.5 py-1.5 text-sm outline-none data-[highlighted]:bg-panel-2">
            <LogOut className="size-4 text-muted" /> Sign out
          </Menu.Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}

export function TopBarActions({ onSearch }: { onSearch: () => void }) {
  const { theme, toggle } = useTheme();
  return (
    <div className="flex items-center gap-1.5">
      <button onClick={onSearch} className="hidden h-8 items-center gap-2 rounded-md border border-line bg-sunken px-2.5 text-sm text-faint hover:border-line-strong md:flex" aria-label="Search (Ctrl+K)">
        <Search className="size-3.5" /> Search
        <kbd className="ml-6 rounded border border-line px-1 font-mono text-[11px]">⌘K</kbd>
      </button>
      <Button variant="ghost" size="icon" className="md:hidden" onClick={onSearch} aria-label="Search"><Search /></Button>
      <Button variant="ghost" size="icon" onClick={toggle} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}>
        {theme === "dark" ? <Sun /> : <Moon />}
      </Button>
      <UserMenu />
    </div>
  );
}

export function AppShell({ children }: { children?: ReactNode }) {
  const [drawer, setDrawer] = useState(false);
  const palette = useCommandPalette();
  const { pathname } = useLocation();
  return (
    <div className="flex min-h-full">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-panel focus:px-3 focus:py-2">Skip to content</a>
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-line bg-bg lg:flex">
        <div className="flex h-14 items-center px-5"><Logo to="/dashboard" /></div>
        <SidebarContent />
      </aside>
      <D.Root open={drawer} onOpenChange={setDrawer}>
        <D.Portal>
          <D.Overlay className="fixed inset-0 z-40 bg-black/50 lg:hidden" />
          <D.Content className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-line bg-bg lg:hidden" aria-describedby={undefined}>
            <D.Title className="sr-only">Navigation</D.Title>
            <div className="flex h-14 items-center px-5"><Logo to="/dashboard" /></div>
            <SidebarContent onNavigate={() => setDrawer(false)} />
          </D.Content>
        </D.Portal>
      </D.Root>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-bg/85 px-4 backdrop-blur sm:px-6">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setDrawer(true)} aria-label="Open navigation"><MenuIcon /></Button>
          <div className="lg:hidden"><Logo to="/dashboard" /></div>
          <div className="ml-auto"><TopBarActions onSearch={() => palette.setOpen(true)} /></div>
        </header>
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 lg:px-10"><ErrorBoundary resetKey={pathname}>{children ?? <Outlet />}</ErrorBoundary></main>
      </div>
      <CommandPalette open={palette.open} onOpenChange={palette.setOpen} />
    </div>
  );
}
