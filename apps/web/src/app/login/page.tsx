"use client";

import { Button, Field, Input } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@agrayian/sdk";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("admin@agrayian.demo");
  const [password, setPassword] = useState("Agrarian!Demo1");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await login(email, password);
      router.replace("/");
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setError(
          "Too many sign-in attempts. Wait a few minutes and try again.",
        );
      } else if (error instanceof ApiError && error.status === 401) {
        setError("Those credentials were declined.");
      } else {
        setError(error instanceof Error ? error.message : "Sign-in failed.");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="auth">
      <section className="auth-story">
        <div className="brand">
          <span className="brand-mark"><i /><i /><i /></span>
          Sales Engine
        </div>
        <div>
          <h1>Run the full revenue lifecycle in one workspace.</h1>
          <p>Find accounts, run campaigns, qualify demand, and keep customers. Humans own the relationship. The system keeps the rhythm.</p>
        </div>
        <p className="small">AGRAYIAN AI Labs · SSO is not configured</p>
      </section>
      <section className="auth-form">
        <form className="auth-box" onSubmit={onSubmit}>
          <div>
            <p className="eyebrow">Sign in</p>
            <h1>Welcome back</h1>
            <p className="muted" style={{ marginTop: 8 }}>Use your workspace credentials. Single sign-on is not configured.</p>
          </div>
          <Field label="Email">
            <Input value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Password">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          {error ? <p className="tag bad">{error}</p> : null}
          <Button disabled={pending}>{pending ? "Signing in…" : "Sign in"}</Button>
        </form>
      </section>
    </div>
  );
}
