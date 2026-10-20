"use client";

import Panel from "./Panel";
import { formatPercent } from "@/lib/format";
import { useAppData } from "@/providers/AppDataProvider";
import type { Position } from "@/lib/types";

/** Tint a position cell green (profit) / red (loss), intensity by |return %|. */
function tint(returnPercent: number): string {
  const alpha = Math.min(0.15 + Math.abs(returnPercent) / 20, 0.85);
  const base = returnPercent >= 0 ? "38, 166, 107" : "229, 72, 77";
  return `rgba(${base}, ${alpha.toFixed(2)})`;
}

/** Positions sized by weight (positions-only denominator), colored by P&L. */
export default function Heatmap() {
  const { portfolio } = useAppData();
  const positions = portfolio?.positions ?? [];
  const total = positions.reduce((sum, p) => sum + p.market_value, 0);

  return (
    <Panel title="Portfolio Heatmap" className="h-full">
      {positions.length === 0 || total === 0 ? (
        <div className="flex h-full min-h-[140px] items-center justify-center text-sm text-fg-muted">
          No positions yet.
        </div>
      ) : (
        <div className="flex h-full min-h-[140px] flex-wrap content-start gap-1 p-1">
          {positions.map((p) => (
            <HeatCell key={p.ticker} position={p} weight={p.market_value / total} />
          ))}
        </div>
      )}
    </Panel>
  );
}

function HeatCell({ position, weight }: { position: Position; weight: number }) {
  return (
    <div
      className="flex min-w-[88px] flex-col justify-center rounded px-2 py-3 text-center"
      style={{ flexGrow: Math.max(weight * 100, 1), flexBasis: 0, background: tint(position.return_percent) }}
      title={`${position.ticker} · ${(weight * 100).toFixed(1)}% of positions`}
    >
      <div className="font-mono text-sm font-semibold">{position.ticker}</div>
      <div className="font-mono text-xs tabular-nums">{formatPercent(position.return_percent)}</div>
    </div>
  );
}
