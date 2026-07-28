import type { ReactNode } from "react";

interface ChartCardProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
}

/** Shared card wrapper so all charts get consistent chrome. */
export default function ChartCard({ title, subtitle, children }: ChartCardProps) {
  return (
    <section className="rounded-lg border border-stone-200 bg-white p-4">
      <h2 className="text-sm font-semibold">{title}</h2>
      {subtitle && <p className="mb-2 text-xs text-stone-500">{subtitle}</p>}
      {children}
    </section>
  );
}
