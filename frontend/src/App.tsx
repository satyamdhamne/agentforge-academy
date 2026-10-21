import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { AppShell } from "./components/layout/AppShell";
import { PageSkeleton } from "./components/ui/skeleton";
import { useAuth } from "./lib/auth";
import Landing from "./pages/Landing";

const Login = lazy(() => import("./pages/auth/Login"));
const Register = lazy(() => import("./pages/auth/Register"));
const VerifyEmail = lazy(() => import("./pages/auth/VerifyEmail"));
const ForgotPassword = lazy(() => import("./pages/auth/ForgotPassword"));
const ResetPassword = lazy(() => import("./pages/auth/ResetPassword"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Paths = lazy(() => import("./pages/Paths"));
const PathDetail = lazy(() => import("./pages/PathDetail"));
const LessonPage = lazy(() => import("./pages/Lesson"));
const CodeLab = lazy(() => import("./pages/CodeLab"));
const Challenges = lazy(() => import("./pages/Challenges"));
const ChallengeWorkspace = lazy(() => import("./pages/ChallengeWorkspace"));
const Agents = lazy(() => import("./pages/Agents"));
const AgentDetail = lazy(() => import("./pages/AgentDetail"));
const Projects = lazy(() => import("./pages/Projects"));
const ProgressPage = lazy(() => import("./pages/Progress"));
const Settings = lazy(() => import("./pages/Settings"));
const Pricing = lazy(() => import("./pages/Pricing"));
const Planned = lazy(() => import("./pages/Planned"));
const Admin = lazy(() => import("./pages/admin/Admin"));
const NotFound = lazy(() => import("./pages/NotFound"));
const PromptLab = lazy(() => import("./pages/labs/PromptLab"));
const RagLab = lazy(() => import("./pages/labs/RagLab"));
const ModelsLab = lazy(() => import("./pages/labs/ModelsLab"));
const EvaluationsList = lazy(() => import("./pages/Evaluations").then((m) => ({ default: m.EvaluationsList })));
const EvaluationDetail = lazy(() => import("./pages/Evaluations").then((m) => ({ default: m.EvaluationDetail })));
const EvaluationCompare = lazy(() => import("./pages/Evaluations").then((m) => ({ default: m.EvaluationCompare })));
const BuilderHome = lazy(() => import("./pages/builder/BuilderHome"));
const BuilderStudio = lazy(() => import("./pages/builder/BuilderStudio"));
const InterviewsHome = lazy(() => import("./pages/Interviews").then((m) => ({ default: m.InterviewsHome })));
const InterviewTrack = lazy(() => import("./pages/Interviews").then((m) => ({ default: m.InterviewTrack })));
const InterviewSession = lazy(() => import("./pages/Interviews").then((m) => ({ default: m.InterviewSession })));
const PortfolioPage = lazy(() => import("./pages/Portfolio"));
const PublicPortfolio = lazy(() => import("./pages/Portfolio").then((m) => ({ default: m.PublicPortfolio })));
const Mentor = lazy(() => import("./pages/Mentor"));

function RequireAuth({ children, staff }: { children: ReactNode; staff?: boolean }) {
  const { user, loading, isStaff } = useAuth();
  const loc = useLocation();
  if (loading) return <PageSkeleton />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  if (staff && !isStaff) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

function ScrollToTop() {
  const { pathname } = useLocation();
  // Braces matter: in current Chrome window.scrollTo returns a Promise, and React would call it as a cleanup.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

export function App() {
  const { pathname } = useLocation();
  return (
    <ErrorBoundary resetKey={pathname}>
      <ScrollToTop />
      <Suspense fallback={<div className="p-10"><PageSkeleton /></div>}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/u/:slug" element={<PublicPortfolio />} />
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
            <Route path="/paths" element={<Paths />} />
            <Route path="/paths/:slug" element={<PathDetail />} />
            <Route path="/lessons/:slug" element={<LessonPage />} />
            <Route path="/lab" element={<CodeLab />} />
            <Route path="/challenges" element={<Challenges />} />
            <Route path="/challenges/:slug" element={<ChallengeWorkspace />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/agents/:slug" element={<AgentDetail />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/pricing" element={<Pricing />} />
            <Route path="/progress" element={<RequireAuth><ProgressPage /></RequireAuth>} />
            <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
            <Route path="/labs/prompts" element={<PromptLab />} />
            <Route path="/labs/prompts/:slug" element={<PromptLab />} />
            <Route path="/labs/rag" element={<RagLab />} />
            <Route path="/labs/models" element={<ModelsLab />} />
            <Route path="/evaluations" element={<RequireAuth><EvaluationsList /></RequireAuth>} />
            <Route path="/evaluations/compare" element={<RequireAuth><EvaluationCompare /></RequireAuth>} />
            <Route path="/evaluations/:id" element={<RequireAuth><EvaluationDetail /></RequireAuth>} />
            <Route path="/builder" element={<RequireAuth><BuilderHome /></RequireAuth>} />
            <Route path="/builder/:id" element={<RequireAuth><BuilderStudio /></RequireAuth>} />
            <Route path="/interviews" element={<InterviewsHome />} />
            <Route path="/interviews/session/:id" element={<RequireAuth><InterviewSession /></RequireAuth>} />
            <Route path="/interviews/:track" element={<InterviewTrack />} />
            <Route path="/portfolio" element={<RequireAuth><PortfolioPage /></RequireAuth>} />
            <Route path="/mentor" element={<RequireAuth><Mentor /></RequireAuth>} />
            <Route path="/soon/:key" element={<Planned />} />
            <Route path="/admin/*" element={<RequireAuth staff><Admin /></RequireAuth>} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
