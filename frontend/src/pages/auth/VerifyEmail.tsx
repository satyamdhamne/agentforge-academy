import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { AuthLayout, FormError } from "./AuthLayout";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const { refresh } = useAuth();
  const [state, setState] = useState<"working" | "done" | "error">("working");
  const [error, setError] = useState<string | null>(null);
  const sent = useRef(false);
  useEffect(() => {
    const token = params.get("token");
    if (sent.current) return;
    sent.current = true;
    if (!token) { setState("error"); setError("This link is missing its token."); return; }
    api.post("/auth/verify-email", { token })
      .then(() => { setState("done"); refresh(); })
      .catch((e) => { setState("error"); setError(errorMessage(e)); });
  }, [params, refresh]);
  return (
    <AuthLayout title={state === "done" ? "Email verified" : state === "error" ? "Couldn’t verify your email" : "Verifying your email…"}>
      {state === "done" && <p className="text-muted">Thanks - your address is confirmed. <Link to="/dashboard" className="text-signal hover:underline">Go to your dashboard</Link>.</p>}
      {state === "error" && (
        <div className="space-y-3">
          <FormError message={error} />
          <p className="text-sm text-muted">Sign in and request a new link from <Link to="/settings" className="text-signal hover:underline">settings</Link>.</p>
        </div>
      )}
    </AuthLayout>
  );
}
