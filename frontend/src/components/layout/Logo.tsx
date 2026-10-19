import { Link } from "react-router-dom";

export function Logo({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className="flex items-center gap-2 rounded font-display text-[17px] font-semibold tracking-tight">
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
        <rect width="32" height="32" rx="7" className="fill-panel-2" />
        <path d="M7 21h6l3-10 3 14 3-8h3" fill="none" stroke="var(--signal)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      AgentForge<span className="hidden font-normal text-muted sm:inline">Academy</span>
    </Link>
  );
}
