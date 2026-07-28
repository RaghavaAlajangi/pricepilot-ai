import Dashboard from "@/components/Dashboard";

export default function HomePage() {
  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-bold">PricePilot AI</h1>
        <p className="mt-1 text-sm text-stone-500">
          Price-demand modelling and AI agent analysis over two years of daily
          sales (60 products &middot; DE / FR / CH)
        </p>
      </header>
      <Dashboard />
    </main>
  );
}
