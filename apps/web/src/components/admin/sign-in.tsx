"use client";

import { useState, type FormEvent } from "react";

import { Panel } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { useAuth } from "@/lib/auth";

export function SignIn({ problem }: { problem?: string }) {
  const auth = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (auth.method === "supabase") await auth.signIn(email, password);
      else auth.setToken(token.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel className="mx-auto w-full max-w-md p-6">
      <h1 className="font-wide text-2xl font-bold tracking-tight">Sign in to admin</h1>
      <p className="mt-1 text-sm text-ink-2">
        {auth.method === "supabase"
          ? "Use the Supabase account whose email is in the API's ADMIN_EMAILS."
          : "Enter the API's ADMIN_API_TOKEN. It's kept only for this browser tab."}
      </p>
      {problem ? (
        <p className="mt-4 rounded-[5px] border border-loss/40 px-3 py-2 text-sm text-loss" role="alert">
          {problem}
        </p>
      ) : null}
      <form onSubmit={submit} className="mt-5 flex flex-col gap-4">
        {auth.method === "supabase" ? (
          <>
            <Field label="Email" htmlFor="email">
              <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Password" htmlFor="password">
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
          </>
        ) : (
          <Field label="Admin token" htmlFor="token">
            <Input id="token" type="password" autoComplete="off" required value={token} onChange={(e) => setToken(e.target.value)} />
          </Field>
        )}
        {error ? (
          <p className="text-sm text-loss" role="alert">
            {error}
          </p>
        ) : null}
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "Signing in" : "Sign in"}
        </Button>
      </form>
    </Panel>
  );
}
