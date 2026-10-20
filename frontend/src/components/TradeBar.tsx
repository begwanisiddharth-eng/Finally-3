"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAppData } from "@/providers/AppDataProvider";

/** Market-order entry: ticker, quantity, buy/sell. Instant fill (section 10). */
export default function TradeBar({ selected }: { selected: string | null }) {
  const { refreshAfterTrade } = useAppData();
  // Follows the selected watchlist ticker until the user types an override.
  const [override, setOverride] = useState<string | null>(null);
  const ticker = override ?? selected ?? "";
  const [qty, setQty] = useState("1");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  const flash = (text: string, ok: boolean) => {
    setMsg({ text, ok });
    setTimeout(() => setMsg(null), 4000);
  };

  const submit = async (side: "buy" | "sell") => {
    const sym = ticker.trim().toUpperCase();
    const quantity = Number(qty);
    if (!sym || busy) return;
    setBusy(true);
    try {
      const { trade } = await api.trade(sym, side, quantity);
      flash(`${side === "buy" ? "Bought" : "Sold"} ${trade.quantity} ${trade.ticker} @ ${trade.price}`, true);
      await refreshAfterTrade();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "Trade failed", false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-panel px-3 py-2">
      <span className="text-xs font-semibold uppercase tracking-wider text-fg-muted">Trade</span>
      <input
        value={ticker}
        onChange={(e) => setOverride(e.target.value)}
        placeholder="Ticker"
        className="w-28 rounded border border-border bg-bg px-2 py-1 text-sm uppercase outline-none focus:border-blue"
      />
      <input
        value={qty}
        onChange={(e) => setQty(e.target.value)}
        type="number"
        min="0"
        step="any"
        placeholder="Qty"
        className="w-24 rounded border border-border bg-bg px-2 py-1 text-sm tabular-nums outline-none focus:border-blue"
      />
      <button
        onClick={() => submit("buy")}
        disabled={busy}
        className="rounded bg-up px-4 py-1 text-sm font-semibold text-black disabled:opacity-50"
      >
        Buy
      </button>
      <button
        onClick={() => submit("sell")}
        disabled={busy}
        className="rounded bg-down px-4 py-1 text-sm font-semibold text-black disabled:opacity-50"
      >
        Sell
      </button>
      {msg && (
        <span className={`text-xs ${msg.ok ? "text-up" : "text-down"}`}>{msg.text}</span>
      )}
    </div>
  );
}
