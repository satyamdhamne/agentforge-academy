import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "./CodeBlock";
import { cn } from "@/lib/utils";

export function Markdown({ children, className }: { children: string | null | undefined; className?: string }) {
  if (!children) return null;
  return (
    <div className={cn("prose-af", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => <>{children}</>,
          code: ({ className: cls, children: code }) => {
            const m = /language-(\w+)/.exec(cls || "");
            const text = String(code ?? "");
            if (m || text.includes("\n")) return <CodeBlock code={text} language={m?.[1] ?? "text"} className="my-3" />;
            return <code>{code}</code>;
          },
          a: ({ href, children: c }) => (
            <a href={href} target={href?.startsWith("http") ? "_blank" : undefined} rel="noreferrer noopener">{c}</a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
