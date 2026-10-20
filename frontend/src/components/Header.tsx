"use client";

import { useState } from "react";
import { formatMoney } from "@/lib/format";
import { useAppData } from "@/providers/AppDataProvider";
import { usePrices, type ConnectionState } from "@/providers/PricesProvider";

const DOT: Record<ConnectionState, string> = {
  connected: "bg-up",
  reconnecting: "bg-accent",
  disconnected: "bg-down",
};

export default function Header() {
  const { portfolio, health, resetAll } = useAppData();
  const { prices, connection } = usePrices();
  const [confirming, setConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);

  const doReset = async () => {
    setResetting(true);
    try {
      await resetAll();
      setConfirming(false);
    } finally {
      setResetting(false);
    }
  };

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

        <button
          onClick={() => setConfirming(true)}
          className="rounded-md border border-down bg-down/15 px-4 py-1.5 text-sm font-bold uppercase tracking-wider text-down hover:bg-down hover:text-black"
        >
          Reset
        </button>
      </div>

      {confirming && (
        <ResetDialog busy={resetting} onCancel={() => setConfirming(false)} onConfirm={doReset} />
      )}
    </header>
  );
}

function ResetDialog({
  busy,
  onCancel,
  onConfirm,
}: {
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-panel p-5 shadow-xl">
        <h3 className="text-base font-semibold">Reset portfolio?</h3>
        <p className="mt-2 text-sm text-fg-muted">
          This resets cash to Rs 10,00,000, clears all positions and trades, restores the default
          watchlist, and empties the chat — exactly like a first launch. This cannot be undone.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={busy}
            className="rounded border border-border px-4 py-1.5 text-sm text-fg hover:bg-panel-alt disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={busy}
            className="rounded bg-down px-4 py-1.5 text-sm font-semibold text-black disabled:opacity-50"
          >
            {busy ? "Resetting…" : "Reset"}
          </button>
        </div>
      </div>
    </div>
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
