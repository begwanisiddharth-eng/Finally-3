/** Display formatting helpers. Money is in rupees. */

const rupee = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Rs 10,00,000.00 style, Indian grouping. */
export function formatMoney(value: number | null | undefined): string {
  if (value == null) return "—";
  return `Rs ${rupee.format(value)}`;
}

/** Bare number with 2dp and Indian grouping (no currency prefix). */
export function formatNumber(value: number | null | undefined): string {
  if (value == null) return "—";
  return rupee.format(value);
}

/** Signed percent, e.g. +1.35% / -0.42%. */
export function formatPercent(value: number | null | undefined): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

/** Signed money delta, e.g. +10.00 / -4.50. */
export function formatSigned(value: number | null | undefined): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${rupee.format(value)}`;
}

/** Trim trailing zeros for share quantities (fractional allowed). */
export function formatQty(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/\.?0+$/, "");
}

/** Local time HH:MM:SS from a UTC ISO string. */
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString();
}

/** Tailwind text color class for a signed value. */
export function pnlClass(value: number | null | undefined): string {
  if (value == null || value === 0) return "text-fg-muted";
  return value > 0 ? "text-up" : "text-down";
}
