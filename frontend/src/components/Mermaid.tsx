import { useEffect, useId, useState } from "react";
import { CodeBlock } from "./CodeBlock";

/** Renders a Mermaid diagram (lazy-loads mermaid). Falls back to showing the source if rendering fails. */
export function Mermaid({ chart }: { chart: string }) {
  const id = useId().replace(/:/g, "");
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    import("mermaid").then(async ({ default: mermaid }) => {
      const css = getComputedStyle(document.documentElement);
      const v = (n: string) => css.getPropertyValue(n).trim();
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: "base",
        fontFamily: "Instrument Sans Variable, sans-serif",
        themeVariables: {
          primaryColor: v("--panel-2"), primaryTextColor: v("--fg"), primaryBorderColor: v("--line-strong"),
          lineColor: v("--fg-muted"), secondaryColor: v("--panel"), tertiaryColor: v("--panel"), fontSize: "14px",
        },
      });
      try {
        const { svg: out } = await mermaid.render(`m${id}`, chart);
        if (!cancelled) setSvg(out);
      } catch {
        if (!cancelled) setFailed(true);
      }
    });
    return () => { cancelled = true; };
  }, [chart, id]);
  if (failed) return <CodeBlock code={chart} language="text" />;
  if (!svg) return <div className="h-40 animate-pulse rounded-md bg-panel-2" aria-label="Loading diagram" />;
  return <div className="overflow-x-auto rounded-md border border-line bg-sunken p-4 [&_svg]:mx-auto [&_svg]:max-w-full" dangerouslySetInnerHTML={{ __html: svg }} />;
}
