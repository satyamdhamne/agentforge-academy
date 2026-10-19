import {
  Award, BookOpen, Bot, Boxes, BrainCircuit, Building2, Cloud, Code2, Database, FolderGit2, GraduationCap,
  LayoutDashboard, MessageSquareQuote, Network, Shield, Swords, Trophy, Users, Workflow, type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  /** Planned items link to a roadmap page that says what ships when and what to use today. */
  planned?: { phase: string; summary: string; meanwhile: { label: string; to: string }[] };
  auth?: boolean;
}

export const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Learn",
    items: [
      { label: "Dashboard", to: "/dashboard", icon: LayoutDashboard, auth: true },
      { label: "Learning Paths", to: "/paths", icon: GraduationCap },
      { label: "Interactive Coding Lab", to: "/lab", icon: Code2 },
      { label: "Daily Challenges", to: "/challenges", icon: Swords },
      { label: "Real-World Projects", to: "/projects", icon: FolderGit2 },
    ],
  },
  {
    group: "Build with AI",
    items: [
      { label: "AI Agent Library", to: "/agents", icon: Bot },
      {
        label: "Agent Builder Studio", to: "/soon/agent-builder", icon: Workflow,
        planned: { phase: "Phase 5", summary: "A visual canvas for input, LLM, prompt, tool, retrieval, condition, memory, approval, evaluation and output nodes - validated graphs, an allowlisted node registry, server-side execution with budgets, timeouts and approval gates.",
          meanwhile: [{ label: "Study the reference agents and their traces", to: "/agents?implemented=true" }, { label: "Solve the workflow DAG challenge", to: "/challenges/py-workflow-execution-order" }] },
      },
      {
        label: "RAG Engineering Lab", to: "/soon/rag-lab", icon: Database,
        planned: { phase: "Phase 4", summary: "An interactive Upload → Parse → Chunk → Embed → Index → Retrieve → Rerank → Generate → Cite → Evaluate pipeline on pgvector with tunable chunking, top-k and search strategy.",
          meanwhile: [{ label: "Chunking strategies lesson", to: "/lessons/rag-chunking-strategies" }, { label: "Run the PDF Knowledge Agent", to: "/agents/pdf-knowledge-agent" }, { label: "RAG tuning challenges", to: "/challenges?category=rag" }] },
      },
      {
        label: "Prompt Engineering Lab", to: "/soon/prompt-lab", icon: MessageSquareQuote,
        planned: { phase: "Phase 4", summary: "Editable prompts with versioning, side-by-side model comparison, scoring rubrics, A/B tests and injection-defence exercises.",
          meanwhile: [{ label: "Prompting challenges", to: "/challenges?category=prompt" }, { label: "Tokens and context windows", to: "/lessons/tokens-context-windows" }] },
      },
      {
        label: "LLM & SLM Lab", to: "/soon/llm-lab", icon: BrainCircuit,
        planned: { phase: "Phase 4", summary: "Model selection by quality, privacy, latency and cost, with CPU-friendly local demos through Ollama-compatible adapters and mock inference.",
          meanwhile: [{ label: "Embeddings and similarity", to: "/lessons/embeddings-similarity" }] },
      },
      {
        label: "Cloud Deployment Lab", to: "/soon/cloud-lab", icon: Cloud,
        planned: { phase: "A later phase", summary: "Guided deployments to AWS (ECS, Lambda, RDS) with Terraform modules, cost estimates and security checks.",
          meanwhile: [{ label: "Weekly project: deployment plan", to: "/challenges/weekly-deploy-fastapi-ecs" }, { label: "Cloud challenges", to: "/challenges?category=cloud" }] },
      },
      {
        label: "System Design Studio", to: "/soon/system-design", icon: Network,
        planned: { phase: "A later phase", summary: "Architecture exercises with diagrams, trade-off analysis and rubric-based reviews.",
          meanwhile: [{ label: "Architecture challenges", to: "/challenges?category=architecture" }] },
      },
    ],
  },
  {
    group: "Grow",
    items: [
      {
        label: "Interview Arena", to: "/soon/interview-arena", icon: Trophy,
        planned: { phase: "Phase 6", summary: "Question banks for 19 tracks and mock interviews scored on accuracy, reasoning, trade-offs and communication with transparent rubrics.",
          meanwhile: [{ label: "Timed interview challenges", to: "/challenges?category=interview" }] },
      },
      {
        label: "Portfolio", to: "/soon/portfolio", icon: Boxes,
        planned: { phase: "Phase 6", summary: "Publish verified projects with repos, diagrams, tests, evaluations and deployment links on a shareable page.",
          meanwhile: [{ label: "Pick a real-world project", to: "/projects" }] },
      },
      {
        label: "Organization Use Cases", to: "/soon/org-use-cases", icon: Building2,
        planned: { phase: "A later phase", summary: "Curated enterprise scenarios showing where agents, workflows, retrieval or plain code fit inside real organisations.",
          meanwhile: [{ label: "Browse agents by business category", to: "/agents" }] },
      },
      {
        label: "Community", to: "/soon/community", icon: Users,
        planned: { phase: "A later phase", summary: "Discussions, solution reviews and study groups.", meanwhile: [{ label: "Today's challenge", to: "/challenges" }] },
      },
      { label: "Progress & Achievements", to: "/progress", icon: Award, auth: true },
    ],
  },
];

export const ADMIN_NAV: NavItem = { label: "Admin CMS", to: "/admin", icon: Shield, auth: true };
export const ALL_ITEMS = NAV.flatMap((g) => g.items);
export { BookOpen };
