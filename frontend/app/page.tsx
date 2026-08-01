import Dashboard from "@/components/Dashboard";

export default function HomePage() {
  return (
    <main className="relative mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {/* soft accent glow behind the header — purely decorative */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(60%_100%_at_50%_0%,rgba(57,135,229,0.14),transparent)]"
      />
      <header className="relative mb-8 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-2xl font-bold tracking-tight">
          <span className="mr-2 inline-block h-3 w-3 rounded-sm bg-accent align-baseline" />
          PricePilot AI
        </h1>
        <p className="text-sm text-ink-muted">
          Price-demand modelling and AI agent analysis over two years of daily
          sales (60 products &middot; DE / FR / CH)
        </p>
      </header>
      <Dashboard />
    </main>
  );
}
