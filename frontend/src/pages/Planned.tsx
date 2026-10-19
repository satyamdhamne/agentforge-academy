import { Link, useParams } from "react-router-dom";
import { ALL_ITEMS } from "@/components/layout/nav";
import NotFound from "./NotFound";

export default function Planned() {
  const { key = "" } = useParams();
  const item = ALL_ITEMS.find((i) => i.to === `/soon/${key}`);
  if (!item?.planned) return <NotFound />;
  return (
    <div className="max-w-2xl">
      <item.icon className="size-8 text-signal" />
      <h1 className="mt-4 text-3xl font-semibold">{item.label}</h1>
      <p className="mt-1 text-sm text-muted">Planned for {item.planned.phase.toLowerCase()} of the roadmap. Not available yet.</p>
      <p className="mt-6 text-lg">{item.planned.summary}</p>
      <h2 className="mt-10 font-display text-lg font-semibold">What you can use today</h2>
      <ul className="mt-3 space-y-2">
        {item.planned.meanwhile.map((m) => <li key={m.to}><Link to={m.to} className="text-signal hover:underline">{m.label}</Link></li>)}
      </ul>
    </div>
  );
}
