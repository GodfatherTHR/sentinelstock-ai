"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { ArrowRight, LockKeyhole, Radio, ShieldCheck } from "lucide-react";
import { createSupabaseBrowserClient } from "@/lib/supabase-browser";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    const supabase = createSupabaseBrowserClient();
    if (!supabase) {
      setMessage("Supabase auth is not configured in this environment. Use demo mode or add the public env values.");
      return;
    }
    setLoading(true);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setLoading(false);
    setMessage(error ? error.message : "Signed in. Redirecting to the network pulse…");
    if (!error) window.location.assign("/");
  }

  return <main className="flex min-h-screen items-center justify-center bg-shell px-5 py-10"><div className="w-full max-w-[420px]"><div className="mb-8 flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-sm border border-mint/35 bg-mint/10 text-mint"><Radio size={19} /></div><div><div className="text-sm font-semibold text-ink">SentinelStock</div><div className="mono text-[9px] uppercase tracking-[.14em] text-muted">AI / OPS CONSOLE</div></div></div><div className="panel rounded-sm p-6 shadow-glow"><span className="eyebrow">Secure operator access</span><h1 className="mt-3 text-2xl font-medium tracking-[-.04em] text-ink">Sign in to the network pulse.</h1><p className="mt-2 text-sm leading-6 text-muted">Use your Supabase-authenticated operator account to access tenant-scoped inventory and approvals.</p><form className="mt-7 space-y-4" onSubmit={submit}><label className="block"><span className="eyebrow">Work email</span><input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="mt-2 w-full rounded-sm border border-seam bg-shell px-3 py-2.5 text-sm text-ink outline-none placeholder:text-muted/60 focus:border-ice/50" placeholder="manager@company.com" /></label><label className="block"><span className="eyebrow">Password</span><div className="relative"><LockKeyhole size={14} className="absolute left-3 top-3 text-muted" /><input required type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="mt-2 w-full rounded-sm border border-seam bg-shell py-2.5 pl-9 pr-3 text-sm text-ink outline-none placeholder:text-muted/60 focus:border-ice/50" placeholder="••••••••" /></div></label>{message && <p className="rounded-sm border border-orange/25 bg-orange/10 px-3 py-2.5 text-xs leading-5 text-orange">{message}</p>}<button disabled={loading} className="flex w-full items-center justify-center gap-2 rounded-sm bg-mint px-4 py-3 text-xs font-semibold text-shell transition-colors hover:bg-white disabled:cursor-wait disabled:opacity-60">{loading ? "Authenticating…" : "Sign in"}<ArrowRight size={14} /></button></form><div className="mt-5 flex items-start gap-2 border-t border-seam pt-4 text-[10px] leading-5 text-muted"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-mint" />Role and organization policies are enforced in Supabase RLS and the backend approval service.</div></div><Link href="/" className="mt-5 block text-center text-xs text-muted hover:text-ice">Continue in demo mode <ArrowRight size={13} className="ml-1 inline" /></Link></div></main>;
}
