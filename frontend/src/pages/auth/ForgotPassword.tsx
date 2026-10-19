import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { AuthLayout, FormError } from "./AuthLayout";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.post<{ message: string }>("/auth/password-reset/request", { email });
      setMessage(r.message);
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  return (
    <AuthLayout title="Reset your password" subtitle="We’ll email you a link that works for 30 minutes." footer={<Link className="text-signal hover:underline" to="/login">Back to sign in</Link>}>
      {message ? (
        <p className="rounded-md border border-line bg-panel p-3 text-sm">{message}</p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <FormError message={error} />
          <div>
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <Button type="submit" className="w-full">Send reset link</Button>
        </form>
      )}
    </AuthLayout>
  );
}
