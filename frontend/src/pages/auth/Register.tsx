import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { User } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { AuthLayout, FormError } from "./AuthLayout";

export default function Register() {
  const nav = useNavigate();
  const { setUser } = useAuth();
  const [form, setForm] = useState({ display_name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (form.password.length < 10) return setError("Use at least 10 characters for your password.");
    setBusy(true);
    setError(null);
    try {
      const u = await api.post<User>("/auth/register", form);
      setUser(u);
      nav("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError && err.code === "validation_error" ? "Check your email address and name." : errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Free plan: introductory tracks, selected challenges and mock agent runs."
      footer={<>Already have an account? <Link className="text-signal hover:underline" to="/login">Sign in</Link></>}
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <FormError message={error} />
        <div>
          <Label htmlFor="name">Name</Label>
          <Input id="name" autoComplete="name" required value={form.display_name} onChange={set("display_name")} />
        </div>
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" required value={form.email} onChange={set("email")} />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="new-password" required minLength={10} value={form.password} onChange={set("password")} aria-describedby="pw-help" />
          <p id="pw-help" className="mt-1 text-xs text-faint">At least 10 characters. A passphrase works well.</p>
        </div>
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Creating account…" : "Create account"}</Button>
        <p className="text-xs text-faint">We store only what we need to track your learning. You can turn the AI mentor and public portfolio on or off in settings.</p>
      </form>
    </AuthLayout>
  );
}
