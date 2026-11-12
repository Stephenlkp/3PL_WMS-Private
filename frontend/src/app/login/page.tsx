"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { BrandMark } from "@/components/brand";
import { ApiError, apiBase, saveSession } from "@/lib/api";
import { Button, Field } from "@/components/ui";

const demo = [
  ["admin@wms.local", "Admin"],
  ["picker@wms.local", "Picker"],
  ["packer@wms.local", "Packer"],
  ["ispring@wms.local", "iSpring"],
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("picker@wms.local");
  const [password, setPassword] = useState("Wms-demo-123");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const showDemo = process.env.NEXT_PUBLIC_DEMO_HINTS !== "false";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const response = await fetch(`${apiBase()}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const raw = await response.text();
      let body: { detail?: string; code?: string; access_token?: string } = {};
      try {
        body = raw ? JSON.parse(raw) : {};
      } catch {
        throw new ApiError(response.status, "Login failed");
      }
      if (!response.ok) throw new ApiError(response.status, body.detail || "Login failed", body.code);
      saveSession(body);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <section className="hidden flex-col justify-between bg-ink p-10 text-paper md:flex">
        <div>
          <BrandMark tone="dark" size="lg" />
          <h1 className="mt-8 max-w-md text-4xl font-semibold leading-tight">Stock moves only when the ledger says it moved.</h1>
        </div>
        <p className="max-w-sm text-sm text-white/70">
          Receive, reserve, pick, pack, then ship. Available stock is physical stock minus what customers have already ordered.
        </p>
      </section>
      <section className="flex items-center justify-center px-6 py-12">
        <form onSubmit={submit} className="w-full max-w-sm space-y-4">
          <div>
            <div className="mb-6 md:hidden">
              <BrandMark size="md" />
            </div>
            <p className="text-xs uppercase tracking-[0.16em] text-amber">StarLinks Logistics</p>
            <h2 className="mt-2 text-2xl font-semibold">Sign in</h2>
          </div>
          <label className="block text-sm">
            Email
            <Field className="mt-1" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" />
          </label>
          <label className="block text-sm">
            Password
            <Field className="mt-1" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </label>
          {error && <p className="text-sm text-brick">{error}</p>}
          <Button className="w-full" disabled={pending}>{pending ? "Signing in…" : "Sign in"}</Button>
          {showDemo && (
            <div className="rounded-2xl border border-line bg-card p-3 text-sm">
              <p className="font-medium">Demo password: Wms-demo-123</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {demo.map(([value, label]) => (
                  <button key={value} type="button" className="rounded-full bg-paper px-3 py-1" onClick={() => setEmail(value)}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </form>
      </section>
    </div>
  );
}
