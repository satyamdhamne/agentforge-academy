import Editor, { loader, type OnMount } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import TsWorker from "monaco-editor/esm/vs/language/typescript/ts.worker?worker";
import { useEffect, useState } from "react";

// Bundle Monaco locally instead of loading it from a CDN.
self.MonacoEnvironment = {
  getWorker: (_: unknown, label: string) => (label === "typescript" || label === "javascript" ? new TsWorker() : new EditorWorker()),
};
loader.config({ monaco });

function defineThemes() {
  const css = getComputedStyle(document.documentElement);
  const v = (n: string) => css.getPropertyValue(n).trim() || "#000000";
  const hex = (n: string) => v(n).replace("#", "");
  for (const [name, base] of [["af-dark", "vs-dark"], ["af-light", "vs"]] as const) {
    monaco.editor.defineTheme(name, {
      base,
      inherit: true,
      rules: [
        { token: "comment", foreground: hex("--fg-faint"), fontStyle: "italic" },
        { token: "keyword", foreground: hex("--llm") },
        { token: "string", foreground: hex("--pass") },
        { token: "number", foreground: hex("--tool") },
      ],
      colors: {
        "editor.background": v("--bg-sunken"),
        "editor.lineHighlightBackground": v("--panel"),
        "editorLineNumber.foreground": v("--fg-faint"),
        "editorGutter.background": v("--bg-sunken"),
      },
    });
  }
}

export interface MonacoProps {
  value: string;
  onChange?: (v: string) => void;
  language: string;
  height?: number | string;
  readOnly?: boolean;
  onRun?: () => void;
  ariaLabel?: string;
}

export default function MonacoEditor({ value, onChange, language, height = 320, readOnly, onRun, ariaLabel }: MonacoProps) {
  const [theme, setTheme] = useState(document.documentElement.dataset.theme === "light" ? "af-light" : "af-dark");
  useEffect(() => {
    const obs = new MutationObserver(() => {
      defineThemes();
      setTheme(document.documentElement.dataset.theme === "light" ? "af-light" : "af-dark");
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);

  const mount: OnMount = (editor) => {
    if (onRun) editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, onRun);
  };
  return (
    <div className="overflow-hidden rounded-md border border-line" aria-label={ariaLabel}>
      <Editor
        height={height}
        language={language === "javascript" ? "javascript" : language}
        value={value}
        theme={theme}
        beforeMount={defineThemes}
        onMount={mount}
        onChange={(v) => onChange?.(v ?? "")}
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 13,
          fontFamily: "'JetBrains Mono Variable', ui-monospace, monospace",
          scrollBeyondLastLine: false,
          tabSize: language === "python" ? 4 : 2,
          automaticLayout: true,
          padding: { top: 10, bottom: 10 },
          renderLineHighlight: readOnly ? "none" : "line",
          ariaLabel: ariaLabel ?? "Code editor",
        }}
      />
    </div>
  );
}
