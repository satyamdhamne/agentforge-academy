import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

interface Props { children: ReactNode; resetKey?: string }
interface State { error: Error | null }

/**
 * Keeps one broken page from blanking the whole app. Resets when `resetKey` changes
 * (the router passes the current path), so navigating away recovers automatically.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[AgentForge] page crashed", error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="mx-auto max-w-lg rounded-lg border border-fail/30 bg-fail/5 p-6">
        <div className="flex gap-3">
          <AlertTriangle className="mt-0.5 size-5 shrink-0 text-fail" />
          <div>
            <p className="font-medium">This page hit an unexpected error.</p>
            <p className="mt-1 text-sm text-muted">Reload to try again. If it keeps happening, report it with this message: {this.state.error.message}</p>
            <button onClick={() => window.location.reload()} className="mt-4 rounded-md border border-line px-3 py-1.5 text-sm hover:bg-panel-2">Reload page</button>
          </div>
        </div>
      </div>
    );
  }
}
