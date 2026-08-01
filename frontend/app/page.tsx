import Dashboard from "@/components/Dashboard";

export default function HomePage() {
  return (
    <main className="relative mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {/* soft accent glow behind the header — purely decorative */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(60%_100%_at_50%_0%,rgba(57,135,229,0.14),transparent)]"
      />
      <header className="relative mb-8 flex flex-wrap items-center justify-between gap-y-2">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="text-2xl font-bold tracking-tight">
            <span className="mr-2 inline-block h-3 w-3 rounded-sm bg-accent align-baseline" />
            PricePilot AI
          </h1>
          <p className="text-sm text-ink-muted">
            Price-demand modelling and AI agent analysis over two years of daily
            sales (60 products &middot; DE / FR / CH)
          </p>
        </div>
        <a
          href="https://github.com/RaghavaAlajangi/pricepilot-ai"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="View source on GitHub"
          className="flex items-center gap-1.5 rounded-md border border-ink-muted/30 px-3 py-1.5 text-xs text-ink-muted transition-colors hover:border-ink-muted/60 hover:text-ink"
        >
          <svg
            aria-hidden
            viewBox="0 0 16 16"
            width="14"
            height="14"
            fill="currentColor"
          >
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
          </svg>
          GitHub
        </a>
      </header>
      <Dashboard />
    </main>
  );
}
