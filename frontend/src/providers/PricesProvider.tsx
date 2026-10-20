"use client";

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { PriceMap } from "@/lib/types";

export type ConnectionState = "connected" | "reconnecting" | "disconnected";

/** One charting point: Unix second (unique, ascending) + price. */
export interface LinePoint {
  time: number;
  value: number;
}

const MAX_POINTS = 900; // ~7.5 min at 2s, ~15 min at 1s — page-lifetime cap

interface PricesContextValue {
  prices: PriceMap;
  connection: ConnectionState;
  /** Accumulated, 1-point-per-second buffer for a ticker (empty if none yet). */
  getBuffer: (ticker: string) => LinePoint[];
  /** Bumps on every SSE frame so chart effects can refresh from the buffer. */
  frame: number;
  /** Drop all accumulated chart history (used by Reset to start charts fresh). */
  clearBuffers: () => void;
}

const PricesContext = createContext<PricesContextValue | null>(null);

export function PricesProvider({ children }: { children: ReactNode }) {
  const [prices, setPrices] = useState<PriceMap>({});
  const [connection, setConnection] = useState<ConnectionState>("reconnecting");
  const [frame, setFrame] = useState(0);
  const buffers = useRef<Map<string, LinePoint[]>>(new Map());

  useEffect(() => {
    const source = new EventSource("/api/stream/prices");

    source.onopen = () => setConnection("connected");
    source.onerror = () => setConnection("reconnecting");

    source.onmessage = (event) => {
      const map = JSON.parse(event.data) as PriceMap;
      for (const [ticker, update] of Object.entries(map)) {
        appendPoint(buffers.current, ticker, Math.floor(update.timestamp), update.price);
      }
      setPrices(map);
      setFrame((f) => f + 1);
    };

    return () => source.close();
  }, []);

  const value: PricesContextValue = {
    prices,
    connection,
    frame,
    getBuffer: (ticker) => buffers.current.get(ticker) ?? [],
    clearBuffers: () => {
      buffers.current.clear();
      setFrame((f) => f + 1);
    },
  };

  return <PricesContext.Provider value={value}>{children}</PricesContext.Provider>;
}

/** Aggregate to one point per second (last price wins), ascending, capped. */
function appendPoint(
  buffers: Map<string, LinePoint[]>,
  ticker: string,
  second: number,
  price: number,
) {
  const points = buffers.get(ticker) ?? [];
  const last = points[points.length - 1];
  if (last && last.time === second) {
    last.value = price;
  } else if (!last || second > last.time) {
    points.push({ time: second, value: price });
    if (points.length > MAX_POINTS) points.shift();
  }
  buffers.set(ticker, points);
}

export function usePrices(): PricesContextValue {
  const ctx = useContext(PricesContext);
  if (!ctx) throw new Error("usePrices must be used within PricesProvider");
  return ctx;
}
