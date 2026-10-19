import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const LEVEL_LABEL: Record<string, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
  expert: "Expert",
};

export const VERDICT_LABEL: Record<string, string> = {
  agent: "Agent",
  workflow: "Workflow",
  rag: "Retrieval pipeline",
  deterministic: "Deterministic code",
};

export const VERDICT_HELP: Record<string, string> = {
  agent: "The path to the answer varies, so a model chooses tools in a bounded loop.",
  workflow: "The steps are known in advance; a fixed pipeline with one or two model calls is cheaper and more reliable.",
  rag: "The hard part is finding the right passages; retrieval with permissions and citations does the work.",
  deterministic: "Rules, statistics or existing scanners solve this exactly; a model at most explains the result.",
};

export const CATEGORY_LABEL: Record<string, string> = {
  coding: "Coding",
  debugging: "Debugging",
  architecture: "Architecture",
  prompt: "Prompting",
  rag: "RAG tuning",
  agent: "Agent reliability",
  security: "Security",
  cloud: "Cloud",
  interview: "Timed interview",
};

export function titleCase(s: string) {
  return s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatDate(iso: string | null | undefined) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function pluralize(n: number, word: string, plural = `${word}s`) {
  return `${n} ${n === 1 ? word : plural}`;
}
