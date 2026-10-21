import {
  Award, BookOpen, Bot, Boxes, BrainCircuit, Building2, Cloud, Code2, Database, FolderGit2, GraduationCap,
  Gauge, LayoutDashboard, MessageSquareQuote, Network, Shield, Sparkles, Swords, Trophy, Users, Workflow, type LucideIcon,
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
      { label: "Agent Builder Studio", to: "/builder", icon: Workflow, auth: true },
      { label: "RAG Engineering Lab", to: "/labs/rag", icon: Database },
      { label: "Prompt Engineering Lab", to: "/labs/prompts", icon: MessageSquareQuote },
      { label: "LLM & SLM Lab", to: "/labs/models", icon: BrainCircuit },
      { label: "Evaluations", to: "/evaluations", icon: Gauge, auth: true },
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
      { label: "Interview Arena", to: "/interviews", icon: Trophy },
      { label: "Portfolio", to: "/portfolio", icon: Boxes, auth: true },
      { label: "AI Mentor", to: "/mentor", icon: Sparkles, auth: true },
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
