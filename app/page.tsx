import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-6xl flex-col px-6 py-10">
      <header className="flex items-center justify-between py-2">
        <div className="text-xl font-semibold tracking-tight">PostOp AI</div>
        <nav className="flex items-center gap-4">
          {/* <Link href="#features" className="text-sm underline">
            Features
          </Link> */}
          <Button asChild variant="primary" size="sm" className="font-mono">
            <Link href="/app">Chat with Maya</Link>
          </Button>
        </nav>
      </header>

      <section className="mt-10 rounded-xl bg-gradient-to-br from-primary to-primary-hover px-8 py-12 text-white">
        <h1 className="text-balance text-4xl font-semibold leading-tight md:text-5xl">
          Automated Patient Follow‑up Calls
        </h1>
        <p className="mt-4 max-w-2xl text-pretty text-lg/7 opacity-90">
          Voice‑enabled AI assistant for post‑operative care. Maya listens during discharge, remembers
          your care plan, and provides personalized reminders and support.
        </p>
        <div className="mt-6">
          <Button asChild variant="secondary" size="lg" className="font-mono">
            <Link href="/app">Chat with Maya</Link>
          </Button>
        </div>
      </section>

      <section id="features" className="mt-12 grid grid-cols-1 gap-6 md:grid-cols-2">
        <article className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <h3 className="text-lg font-semibold">At Discharge</h3>
          <p className="mt-2 text-sm text-fg1">
            Maya listens during your hospital discharge, learning your specific care instructions to
            provide personalized reminders and support.
          </p>
        </article>
        <article className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <h3 className="text-lg font-semibold">Phone Support</h3>
          <p className="mt-2 text-sm text-fg1">
            Call Maya anytime with questions about your recovery, or receive scheduled reminder calls to
            help you follow your care plan.
          </p>
        </article>
        <article className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <h3 className="text-lg font-semibold">Medical Guidance</h3>
          <p className="mt-2 text-sm text-fg1">
            Maya has access to medical knowledge to answer common post‑operative questions and knows when
            to connect you with your care team.
          </p>
        </article>
        <article className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <h3 className="text-lg font-semibold">Personalized Care</h3>
          <p className="mt-2 text-sm text-fg1">
            Automatic reminders tailored to your procedure and recovery timeline to help you stay on
            track.
          </p>
        </article>
      </section>
    </main>
  );
} 