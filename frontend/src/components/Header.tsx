"use client";

import { formatMoney } from "@/lib/format";
import { useAppData } from "@/providers/AppDataProvider";
import { usePrices, type ConnectionState } from "@/providers/PricesProvider";

const DOT: Record<ConnectionState, string> = {
  connected: "bg-up",
  reconnecting: "bg-accent",
  disconnected: "bg-down",
};

export default function Header() {
  const { portfolio, health } = useAppData();
  const { prices, connection } = usePrices();

  // Live equity: held positions valued at the latest streamed prices.
  const liveEquity =
    portfolio == null
      ? null
      : portfolio.positions.reduce((sum, p) => {
          const price = prices[p.ticker]?.price ?? p.current_price ?? p.avg_cost;
          return sum + p.quantity * price;
        }, 0);

  // Live total: cash + equity.
  const liveTotal =
    portfolio == null || liveEquity == null ? null : portfolio.cash_balance + liveEquity;

  const isLive = health?.data_source === "tapetide";
  const healthy = health?.market_data_healthy ?? false;

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-bg-alt px-4 py-2">
      <div className="flex items-center gap-3">
        <span className="text-lg font-bold tracking-tight">
          Fin<span className="text-accent">All</span>y
        </span>
        <span className="text-xs text-fg-muted">AI Trading Workstation</span>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-sm">
        <Badge live={isLive} />
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            healthy ? "bg-up/15 text-up" : "bg-accent/15 text-accent"
          }`}
          title="Market data freshness"
        >
          {healthy ? "Data: live" : "Data: stale"}
        </span>

        <div className="flex items-center gap-1.5" title={`Stream: ${connection}`}>
          <span className={`h-2.5 w-2.5 rounded-full ${DOT[connection]}`} />
          <span className="text-xs capitalize text-fg-muted">{connection}</span>
        </div>

        <div className="text-right">
          <div className="text-[11px] uppercase text-fg-muted">Cash</div>
          <div className="font-mono tabular-nums">{formatMoney(portfolio?.cash_balance)}</div>
        </div>
        <div className="text-right">
          <div className="text-[11px] uppercase text-fg-muted">Equity</div>
          <div className="font-mono tabular-nums">{formatMoney(liveEquity)}</div>
        </div>
        <div className="text-right">
          <div className="text-[11px] uppercase text-fg-muted">Total Value</div>
          <div className="font-mono tabular-nums text-accent">{formatMoney(liveTotal)}</div>
        </div>
      </div>
    </header>
  );
}

function Badge({ live }: { live: boolean }) {
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-bold ${
        live ? "bg-blue/20 text-blue" : "bg-purple/25 text-purple"
      }`}
    >
      {live ? "LIVE (NSE)" : "SIMULATED"}
    </span>
  );
}
