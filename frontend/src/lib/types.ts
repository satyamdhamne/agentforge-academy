export type Level = "beginner" | "intermediate" | "advanced" | "expert";
export type Tier = "free" | "pro" | "team";

export interface User {
  id: string;
  email: string;
  email_verified: boolean;
  roles: string[];
  plan: Tier;
  created_at: string;
  profile: {
    display_name: string;
    bio: string;
    avatar_url: string | null;
    experience_level: Level;
    goals: string[];
    mentor_opt_in: boolean;
    public_portfolio: boolean;
  };
}

export interface TrackSummary {
  slug: string;
  title: string;
  summary: string;
  icon: string;
  color: string;
  level: Level;
  tier: Tier;
  order: number;
  tags: string[];
  courses: number;
  lessons_total: number;
  lessons_available: number;
  lessons_completed: number;
  progress: number;
  enrolled: boolean;
  estimated_hours: number;
}

export interface LessonOutline {
  slug: string;
  title: string;
  summary: string;
  minutes: number;
  level: Level;
  tier: Tier;
  available: boolean;
  locked: boolean;
  completed: boolean;
}

export interface TrackDetail extends TrackSummary {
  description: string;
  outcomes: string[];
  courses_detail: {
    slug: string;
    title: string;
    summary: string;
    level: Level;
    tier: Tier;
    estimated_hours: number;
    modules: { slug: string; title: string; summary: string; lessons: LessonOutline[] }[];
  }[];
}

export interface CodeExample {
  title: string;
  language: "python" | "javascript" | "sql" | "typescript" | "bash" | string;
  runnable?: boolean;
  code: string;
  setup?: string;
  annotations?: string[];
  expected_output?: string;
}

export interface LessonSections {
  explanation: string;
  why_it_matters: string;
  prerequisites: string[];
  mental_model: string;
  architecture?: { caption?: string; mermaid: string } | null;
  code_examples: CodeExample[];
  real_world: string;
  common_mistakes: { mistake: string; fix: string }[];
  debugging: string;
  performance_security: string;
  interview_questions: { q: string; a: string }[];
  mini_challenge: { title: string; prompt: string; exercise?: string };
  advanced_challenge: { title: string; prompt: string };
  further_reading: { title: string; url: string }[];
  version_notes?: string;
}

export interface ExerciseCard {
  slug: string;
  title: string;
  kind: "code" | "multiple_choice" | "manual_review";
  category: string;
  difficulty: Level;
  language: string | null;
  points: number;
  tier: Tier;
  tags: string[];
  time_limit_minutes: number | null;
  is_weekly_project: boolean;
  solved?: boolean;
  locked?: boolean;
}

export interface Lesson {
  slug: string;
  title: string;
  summary: string;
  minutes: number;
  level: Level;
  tier: Tier;
  tags: string[];
  prerequisites: string[];
  breadcrumb: { track: { slug: string; title: string }; course: string; module: string };
  version: number;
  updated_at: string;
  locked: boolean;
  required_tier?: Tier;
  content: { sections: LessonSections } | null;
  navigation?: { prev: { slug: string; title: string } | null; next: { slug: string; title: string } | null };
  progress: { status: "in_progress" | "completed"; quiz_score: number | null; completed_at: string | null } | null;
  quiz: { id: string; prompt: string; options: string[] }[];
  quiz_pass_threshold: number | null;
  exercises: ExerciseCard[];
}

export interface Achievement {
  slug: string;
  name: string;
  icon: string;
  description?: string;
  earned?: boolean;
  awarded_at?: string | null;
}

export interface Dashboard {
  stats: { lessons_completed: number; challenges_solved: number; points: number; streak_days: number; agent_runs: number };
  continue_lesson: { slug: string; title: string; track: string } | null;
  enrolled_tracks: TrackSummary[];
  recommended_tracks: TrackSummary[];
  daily_challenge: ExerciseCard | null;
  activity: { date: string; count: number }[];
  recent_achievements: Achievement[];
  plan: Tier;
}

export interface TestResult {
  index: number;
  passed: boolean;
  hidden: boolean;
  args?: unknown[];
  expected?: unknown;
  actual?: unknown;
  error?: string;
}

export interface ChallengeDetail extends ExerciseCard {
  locked: boolean;
  required_tier?: Tier;
  prompt_md: string;
  starter_code: string;
  hints_total: number;
  hints: { index: number; text: string }[];
  public_tests: { args: unknown[]; expected: unknown }[];
  hidden_tests: number;
  options: string[] | null;
  rubric: { criterion: string; weight?: number; description: string }[] | null;
  min_words: number | null;
  sql_setup: string | null;
  execution: "sandbox" | "unavailable" | "none";
  attempts: number;
  solved: boolean;
  points_earned: number;
  hints_revealed: number[];
  pending_review?: boolean;
  explanation_md?: string;
  solution?: string;
}

export interface Attempt {
  id: string;
  status: "passed" | "failed" | "error" | "not_graded" | "pending_review" | "reviewed";
  score: number;
  points_awarded: number;
  hints_used: number;
  execution_mode: "sandbox" | "unavailable" | "none";
  result: {
    tests_passed?: number;
    tests_total?: number;
    results?: TestResult[];
    compile_error?: string | null;
    stdout?: string;
    stderr?: string;
    timed_out?: boolean;
    duration_ms?: number;
    correct?: boolean;
    message?: string;
    sql?: { columns: string[]; rows: unknown[][] };
    rubric_scores?: Record<string, number>;
  };
  review_feedback: string | null;
  created_at: string;
  reviewed_at: string | null;
  duplicate?: boolean;
  explanation_md?: string;
  solution?: string;
  new_achievements?: Achievement[];
}

export interface AgentCard {
  number: number;
  slug: string;
  name: string;
  category: string;
  level: Level;
  build_hours: number;
  summary: string;
  verdict: "agent" | "workflow" | "rag" | "deterministic";
  has_reference_impl: boolean;
  tier: Tier;
  tags: string[];
}

export interface Span {
  kind: "step" | "llm" | "tool" | string;
  name: string;
  status: "ok" | "error" | string;
  start_ms: number;
  duration_ms: number;
  attributes: Record<string, unknown>;
}

export interface AgentRun {
  id?: string;
  agent?: string | null;
  label?: string;
  status: "running" | "succeeded" | "failed" | "awaiting_approval" | "approved" | "rejected" | "cancelled";
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  pending_actions?: { tool: string; arguments: Record<string, unknown>; reason?: string }[];
  approval_result?: Record<string, unknown> | null;
  trace_id: string;
  trace: Span[];
  provider: string;
  model: string;
  llm_calls: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd?: number | null;
  latency_ms: number;
  error: string | null;
  is_mock?: boolean;
  created_at?: string;
}

export type Blueprint = Record<string, unknown> & {
  problem?: string;
  business_value?: string;
  verdict_reasoning?: string;
  architecture_mermaid?: string;
};

export interface AgentDetail extends AgentCard {
  version: number | null;
  blueprint: Blueprint;
  example_runs: AgentRun[];
  eval_report: {
    cases: number;
    passed: number;
    pass_rate: number | null;
    provider: string;
    generated_at?: string;
    results: { id: string; passed: boolean; status: string; checks: { passed: boolean; check: string }[]; error?: string }[];
  } | null;
  files: string[];
  runnable: boolean;
  examples: Record<string, unknown>[];
  locked: boolean;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page?: number;
  page_size?: number;
}
