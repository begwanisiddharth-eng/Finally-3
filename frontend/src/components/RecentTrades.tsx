"use client";

import Panel from "./Panel";
import { formatNumber, formatQty, formatTime } from "@/lib/format";
import { useAppData } from "@/providers/AppDataProvider";

export default function RecentTrades() {
  const { trades } = useAppData();

  return (
    <Panel title="Recent Trades" className="h-full">
      {trades.length === 0 ? (
        <div className="p-3 text-sm text-fg-muted">No trades yet.</div>
      ) : (
        <ul className="divide-y divide-border-soft/60 text-sm">
          {trades.map((t) => (
            <li key={t.id} className="flex items-center justify-between px-3 py-1.5 font-mono">
              <span
                className={`w-10 font-semibold uppercase ${
                  t.side === "buy" ? "text-up" : "text-down"
                }`}
              >
                {t.side}
              </span>
              <span className="flex-1">{t.ticker}</span>
              <span className="tabular-nums text-fg-muted">{formatQty(t.quantity)}</span>
              <span className="w-24 text-right tabular-nums">{formatNumber(t.price)}</span>
              <span className="w-20 text-right text-xs text-fg-muted">{formatTime(t.executed_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
