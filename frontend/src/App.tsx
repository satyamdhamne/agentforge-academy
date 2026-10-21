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
            <Route path="/soon/:key" element={<Planned />} />
            <Route path="/admin/*" element={<RequireAuth staff><Admin /></RequireAuth>} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
