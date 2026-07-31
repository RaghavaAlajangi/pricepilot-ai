/** Chart color slots (fixed assignment, one hue per role). */
export const CHART_COLORS = {
  price: "#2a78d6", // blue — price series & profit curve
  units: "#eb6834", // orange — demand series
  scatter: "#1baf7a", // aqua — price/demand scatter
  good: "#0ca30c", // status green — recommended price marker
  muted: "#898781", // axis / reference lines
  grid: "#e1e0d9",
} as const;
