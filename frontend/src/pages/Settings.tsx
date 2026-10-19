import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { User } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { PageHeader } from "@/components/States";

export default function Settings() {
  const { user, setUser } = useAuth();
  const p = user!.profile;
  const [form, setForm] = useState({ display_name: p.display_name, bio: p.bio, experience_level: p.experience_level, goals: p.goals.join(", "), mentor_opt_in: p.mentor_opt_in, public_portfolio: p.public_portfolio });
  const save = useMutation({
    mutationFn: () => api.patch<User>("/me/profile", { ...form, goals: form.goals.split(",").map((g) => g.trim()).filter(Boolean).slice(0, 10) }),
    onSuccess: (u) => { setUser(u); toast.success("Settings saved"); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const resend = useMutation({ mutationFn: () => api.post("/auth/resend-verification"), onSuccess: () => toast.success("Verification email sent"), onError: (e) => toast.error(errorMessage(e)) });
  const logoutAll = useMutation({ mutationFn: () => api.post("/auth/logout-all"), onSuccess: () => { setUser(null); window.location.assign("/login"); } });
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(); };
  return (
    <div className="max-w-2xl">
      <PageHeader title="Profile & settings" />
      <form onSubmit={submit} className="space-y-5">
        <div><Label htmlFor="dn">Display name</Label><Input id="dn" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} required maxLength={100} /></div>
        <div><Label htmlFor="bio">Bio</Label><Textarea id="bio" rows={3} value={form.bio} maxLength={1000} onChange={(e) => setForm({ ...form, bio: e.target.value })} /></div>
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <Label htmlFor="lvl">Experience</Label>
            <Select id="lvl" value={form.experience_level} onChange={(e) => setForm({ ...form, experience_level: e.target.value as User["profile"]["experience_level"] })}>
              <option value="beginner">New to coding</option>
              <option value="intermediate">Working developer</option>
              <option value="advanced">Senior engineer</option>
              <option value="expert">Staff and above</option>
            </Select>
          </div>
          <div><Label htmlFor="goals">Goals, comma separated</Label><Input id="goals" value={form.goals} onChange={(e) => setForm({ ...form, goals: e.target.value })} placeholder="RAG, interviews, AWS" /></div>
        </div>
        <fieldset className="space-y-3 rounded-lg border border-line p-4">
          <legend className="px-1 text-sm font-medium">Privacy</legend>
          <label className="flex gap-3 text-sm"><input type="checkbox" className="mt-1 accent-[var(--signal)]" checked={form.mentor_opt_in} onChange={(e) => setForm({ ...form, mentor_opt_in: e.target.checked })} />
            <span><span className="font-medium">AI mentor</span><span className="block text-muted">Let the opt-in tutor read your attempts to give hints. Off by default; it never reveals full solutions unless you ask.</span></span></label>
          <label className="flex gap-3 text-sm"><input type="checkbox" className="mt-1 accent-[var(--signal)]" checked={form.public_portfolio} onChange={(e) => setForm({ ...form, public_portfolio: e.target.checked })} />
            <span><span className="font-medium">Public portfolio</span><span className="block text-muted">Allow a shareable page of your verified projects.</span></span></label>
        </fieldset>
        <Button type="submit" disabled={save.isPending}>Save settings</Button>
      </form>
      <section className="mt-12 space-y-4 border-t border-line pt-8">
        <h2 className="font-display text-lg font-semibold">Account</h2>
        <p className="text-sm text-muted">{user!.email}, {user!.email_verified ? "verified" : "not verified yet"}. Plan: <span className="capitalize">{user!.plan}</span>.</p>
        <div className="flex flex-wrap gap-3">
          {!user!.email_verified && <Button variant="secondary" onClick={() => resend.mutate()} disabled={resend.isPending}>Resend verification email</Button>}
          <Button variant="danger" onClick={() => logoutAll.mutate()}>Sign out of all devices</Button>
        </div>
      </section>
    </div>
  );
}
