import type { ReactNode } from "react";

interface ChartCardProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
}

/** Shared card wrapper so all charts get consistent chrome. */
export default function ChartCard({ title, subtitle, children }: ChartCardProps) {
  return (
    <section className="rounded-xl border border-white/10 bg-surface p-4">
      <h2 className="text-sm font-semibold text-ink">{title}</h2>
      {subtitle && <p className="mb-2 text-xs text-ink-muted">{subtitle}</p>}
      {children}
    </section>
  );
}
