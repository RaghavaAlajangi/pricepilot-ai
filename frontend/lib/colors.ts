/** Chart color slots (fixed assignment, one hue per role) — dark-mode steps
 * of the validated palette (all pairs pass CVD + contrast on #1a1a19). */
export const CHART_COLORS = {
  price: "#3987e5", // blue — price series & profit curve
  units: "#d95926", // orange — demand series
  scatter: "#199e70", // aqua — price/demand scatter
  good: "#0ca30c", // status green — recommended price marker
  muted: "#898781", // axis / reference lines
  grid: "#2c2c2a",
} as const;

/** Shared Recharts tooltip chrome for the dark surface. */
export const TOOLTIP_STYLE = {
  contentStyle: {
    backgroundColor: "#232322",
    border: "1px solid rgba(255,255,255,0.10)",
    borderRadius: 8,
    fontSize: 12,
  },
  labelStyle: { color: "#c3c2b7" },
  itemStyle: { color: "#ffffff" },
} as const;
