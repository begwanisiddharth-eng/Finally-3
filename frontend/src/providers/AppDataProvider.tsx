"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";
import { usePrices } from "@/providers/PricesProvider";
import type { Health, Portfolio, Snapshot, Trade, WatchlistItem } from "@/lib/types";

interface AppDataValue {
  watchlist: WatchlistItem[];
  portfolio: Portfolio | null;
  trades: Trade[];
  history: Snapshot[];
  health: Health | null;
  refreshWatchlist: () => Promise<void>;
  refreshPortfolio: () => Promise<void>;
  refreshTrades: () => Promise<void>;
  refreshHistory: () => Promise<void>;
  /** After a trade or an AI action: portfolio, watchlist, trades, history all move. */
  refreshAfterTrade: () => Promise<void>;
  /** Reset to first-launch state (clears server state + chart buffers). */
  resetAll: () => Promise<void>;
  /** Bumps on each reset so dependent panels (e.g. chat) can clear themselves. */
  resetNonce: number;
}

const AppDataContext = createContext<AppDataValue | null>(null);

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [resetNonce, setResetNonce] = useState(0);
  const { clearBuffers } = usePrices();

  const refreshWatchlist = useCallback(async () => setWatchlist(await api.getWatchlist()), []);
  const refreshPortfolio = useCallback(async () => setPortfolio(await api.getPortfolio()), []);
  const refreshTrades = useCallback(async () => setTrades(await api.getTrades()), []);
  const refreshHistory = useCallback(async () => setHistory(await api.getHistory()), []);

  const refreshAfterTrade = useCallback(async () => {
    await Promise.all([refreshPortfolio(), refreshWatchlist(), refreshTrades(), refreshHistory()]);
  }, [refreshPortfolio, refreshWatchlist, refreshTrades, refreshHistory]);

  const resetAll = useCallback(async () => {
    await api.reset();
    clearBuffers();
    await refreshAfterTrade();
    setResetNonce((n) => n + 1);
  }, [clearBuffers, refreshAfterTrade]);

  // Initial load — fetching from the backend on mount is the intended source
  // of this state (a static SPA has no server-side data loader).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshWatchlist();
    refreshPortfolio();
    refreshTrades();
    refreshHistory();
  }, [refreshWatchlist, refreshPortfolio, refreshTrades, refreshHistory]);

  // Poll health every ~5s (badge + freshness, section 10).
  useEffect(() => {
    const tick = async () => setHealth(await api.getHealth().catch(() => null));
    tick();
    const id = setInterval(tick, 5000);
    return () => clearInterval(id);
  }, []);

  // Poll portfolio value history every ~15s (snapshots land every 30s, section 7).
  useEffect(() => {
    const id = setInterval(() => {
      refreshHistory();
      refreshPortfolio();
    }, 15000);
    return () => clearInterval(id);
  }, [refreshHistory, refreshPortfolio]);

  const value: AppDataValue = {
    watchlist,
    portfolio,
    trades,
    history,
    health,
    refreshWatchlist,
    refreshPortfolio,
    refreshTrades,
    refreshHistory,
    refreshAfterTrade,
    resetAll,
    resetNonce,
  };

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

export function useAppData(): AppDataValue {
  const ctx = useContext(AppDataContext);
  if (!ctx) throw new Error("useAppData must be used within AppDataProvider");
  return ctx;
}
