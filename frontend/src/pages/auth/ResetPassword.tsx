import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { AuthLayout, FormError } from "./AuthLayout";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/auth/password-reset/confirm", { token: params.get("token") ?? "", new_password: password });
      setDone(true);
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  return (
    <AuthLayout title="Choose a new password">
      {done ? (
        <p className="text-muted">Password changed and all other sessions signed out. <Link to="/login" className="text-signal hover:underline">Sign in</Link> with your new password.</p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <FormError message={error} />
          <div>
            <Label htmlFor="password">New password</Label>
            <Input id="password" type="password" autoComplete="new-password" minLength={10} required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <Button type="submit" className="w-full">Change password</Button>
        </form>
      )}
    </AuthLayout>
  );
}
