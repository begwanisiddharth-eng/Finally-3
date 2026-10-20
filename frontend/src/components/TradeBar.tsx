"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAppData } from "@/providers/AppDataProvider";

/** Market-order entry: ticker, quantity, buy/sell. Instant fill (section 10). */
export default function TradeBar({ selected }: { selected: string | null }) {
  const { watchlist, portfolio, refreshAfterTrade } = useAppData();
  // Follows the selected watchlist ticker until the user picks an override.
  const [override, setOverride] = useState<string | null>(null);

  // Tradeable symbols = watchlist U held positions (held-but-unwatched included,
  // so a position off the watchlist can still be sold). Only tracked tickers can
  // be traded (section 6/8), so this is exactly the valid set.
  const tradeable = useMemo(() => {
    const held = (portfolio?.positions ?? []).map((p) => p.ticker);
    return Array.from(new Set([...watchlist.map((w) => w.ticker), ...held]));
  }, [watchlist, portfolio]);

  // Ignore a stale override (e.g. a ticker removed by a reset) and fall back to
  // the current selection.
  const ticker = (override && tradeable.includes(override) ? override : selected) ?? "";
  const [qty, setQty] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  // Clear the quantity whenever a new ticker is selected from the watchlist.
  useEffect(() => {
    setQty("");
  }, [selected]);

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
      <select
        value={ticker}
        onChange={(e) => setOverride(e.target.value)}
        className="w-36 rounded border border-border bg-bg px-2 py-1 text-sm outline-none focus:border-blue"
      >
        <option value="" disabled>
          Select symbol
        </option>
        {tradeable.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
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
