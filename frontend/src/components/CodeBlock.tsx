import { Highlight, type PrismTheme } from "prism-react-renderer";
import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

/** Token colours use the app's CSS variables so code follows the light/dark theme. */
const theme: PrismTheme = {
  plain: { color: "var(--fg)", backgroundColor: "transparent" },
  styles: [
    { types: ["comment", "prolog"], style: { color: "var(--fg-faint)", fontStyle: "italic" } },
    { types: ["keyword", "builtin", "important", "atrule"], style: { color: "var(--llm)" } },
    { types: ["string", "char", "attr-value", "regex", "inserted"], style: { color: "var(--pass)" } },
    { types: ["number", "boolean", "constant"], style: { color: "var(--tool)" } },
    { types: ["function", "class-name", "tag"], style: { color: "var(--signal)" } },
    { types: ["punctuation", "operator"], style: { color: "var(--fg-muted)" } },
    { types: ["deleted"], style: { color: "var(--fail)" } },
  ],
};

const ALIASES: Record<string, string> = { js: "javascript", ts: "typescript", py: "python", sh: "bash", shell: "bash", yml: "yaml", text: "markup" };

export function CodeBlock({ code, language = "text", className, showCopy = true }: { code: string; language?: string; className?: string; showCopy?: boolean }) {
  const [copied, setCopied] = useState(false);
  const lang = ALIASES[language] ?? language;
  return (
    <div className={cn("group relative overflow-hidden rounded-md border border-line bg-sunken", className)}>
      {showCopy && (
        <button
          type="button"
          onClick={() => navigator.clipboard?.writeText(code).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })}
          className="absolute right-2 top-2 rounded p-1 text-faint opacity-0 transition-opacity hover:text-fg focus:opacity-100 group-hover:opacity-100"
          aria-label={copied ? "Copied" : "Copy code"}
        >
          {copied ? <Check className="size-4 text-pass" /> : <Copy className="size-4" />}
        </button>
      )}
      <Highlight code={code.replace(/\n$/, "")} language={lang} theme={theme}>
        {({ tokens, getLineProps, getTokenProps }) => (
          <pre className="overflow-x-auto p-3.5 font-mono text-[13px] leading-[1.6] scrollbar-thin">
            {tokens.map((line, i) => (
              <div key={i} {...getLineProps({ line })}>
                {line.map((token, j) => <span key={j} {...getTokenProps({ token })} />)}
              </div>
            ))}
          </pre>
        )}
      </Highlight>
    </div>
  );
}
