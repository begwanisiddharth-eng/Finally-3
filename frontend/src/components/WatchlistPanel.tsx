"use client";

import { useState, type FormEvent } from "react";
import Panel from "./Panel";
import Sparkline from "./Sparkline";
import { useFlash } from "@/hooks/useFlash";
import { api, ApiError } from "@/lib/api";
import { formatNumber, formatPercent, pnlClass } from "@/lib/format";
import { useAppData } from "@/providers/AppDataProvider";
import { usePrices } from "@/providers/PricesProvider";
import type { WatchlistItem } from "@/lib/types";

interface WatchlistPanelProps {
  selected: string | null;
  onSelect: (ticker: string) => void;
}

export default function WatchlistPanel({ selected, onSelect }: WatchlistPanelProps) {
  const { watchlist, refreshWatchlist } = useAppData();
  const { prices } = usePrices();
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const flash = (msg: string) => {
    setError(msg);
    setTimeout(() => setError(""), 4000);
  };

  const onAdd = async (e: FormEvent) => {
    e.preventDefault();
    const ticker = input.trim().toUpperCase();
    if (!ticker || busy) return;
    setBusy(true);
    try {
      await api.addWatchlist(ticker);
      setInput("");
      await refreshWatchlist();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "Could not add ticker");
    } finally {
      setBusy(false);
    }
  };

  const onRemove = async (ticker: string) => {
    await api.removeWatchlist(ticker).catch(() => {});
    await refreshWatchlist();
  };

  return (
    <Panel title="Watchlist">
      <form onSubmit={onAdd} className="flex gap-2 border-b border-border-soft p-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Add ticker…"
          className="min-w-0 flex-1 rounded border border-border bg-bg px-2 py-1 text-sm uppercase text-fg outline-none focus:border-blue"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-blue px-3 py-1 text-sm font-medium text-black disabled:opacity-50"
        >
          Add
        </button>
      </form>
      {error && <div className="bg-down/15 px-3 py-1.5 text-xs text-down">{error}</div>}
      <table className="w-full text-sm">
        <thead className="text-left text-[11px] uppercase text-fg-muted">
          <tr className="border-b border-border-soft">
            <th className="px-3 py-1.5 font-medium">Ticker</th>
            <th className="px-3 py-1.5 text-right font-medium">Price</th>
            <th className="px-3 py-1.5 text-right font-medium">Day %</th>
            <th className="px-3 py-1.5 text-right font-medium">Trend</th>
            <th className="px-2 py-1.5"></th>
          </tr>
        </thead>
        <tbody>
          {watchlist.map((item) => (
            <WatchlistRow
              key={item.ticker}
              item={item}
              live={prices[item.ticker]}
              selected={item.ticker === selected}
              onSelect={() => onSelect(item.ticker)}
              onRemove={() => onRemove(item.ticker)}
            />
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function WatchlistRow({
  item,
  live,
  selected,
  onSelect,
  onRemove,
}: {
  item: WatchlistItem;
  live?: WatchlistItem;
  selected: boolean;
  onSelect: () => void;
  onRemove: () => void;
}) {
  const price = live?.price ?? item.price;
  const direction = live?.direction ?? item.direction;
  const dayPct = live?.day_change_percent ?? item.day_change_percent;
  const dayChange = live?.day_change ?? item.day_change;
  const flashCls = useFlash(price, direction ?? null);

  return (
    <tr
      onClick={onSelect}
      className={`cursor-pointer border-b border-border-soft/60 hover:bg-panel-alt ${
        selected ? "bg-panel-alt" : ""
      }`}
    >
      <td className="px-3 py-1.5 font-mono font-medium">{item.ticker}</td>
      <td className={`px-3 py-1.5 text-right font-mono tabular-nums ${flashCls}`}>
        {formatNumber(price)}
      </td>
      <td className={`px-3 py-1.5 text-right font-mono tabular-nums ${pnlClass(dayChange)}`}>
        {formatPercent(dayPct)}
      </td>
      <td className="px-3 py-1">
        <div className="flex justify-end">
          <Sparkline ticker={item.ticker} up={(dayChange ?? 0) >= 0} />
        </div>
      </td>
      <td className="px-2 py-1 text-right">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="text-fg-muted hover:text-down"
          aria-label={`Remove ${item.ticker}`}
        >
          ×
        </button>
      </td>
    </tr>
  );
}
