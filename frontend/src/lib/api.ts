/** Same-origin REST client. All API errors use {"error": msg} (section 8). */

import type {
  ChatMessage,
  ChatResponse,
  Health,
  Portfolio,
  Snapshot,
  Trade,
  WatchlistItem,
} from "./types";

/** Error carrying the backend's human-readable message and HTTP status. */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const msg = body?.error ?? `Request failed (${res.status})`;
    throw new ApiError(msg, res.status);
  }
  return body as T;
}

export const api = {
  getWatchlist: () =>
    request<{ tickers: WatchlistItem[] }>("/api/watchlist").then((r) => r.tickers),
  addWatchlist: (ticker: string) =>
    request<{ ticker: string; added_at: string }>("/api/watchlist", {
      method: "POST",
      body: JSON.stringify({ ticker }),
    }),
  removeWatchlist: (ticker: string) =>
    request<{ ticker: string; removed: boolean }>(
      `/api/watchlist/${encodeURIComponent(ticker)}`,
      { method: "DELETE" },
    ),

  getPortfolio: () => request<Portfolio>("/api/portfolio"),
  trade: (ticker: string, side: "buy" | "sell", quantity: number) =>
    request<{ trade: Trade; portfolio: Portfolio }>("/api/portfolio/trade", {
      method: "POST",
      body: JSON.stringify({ ticker, side, quantity }),
    }),
  getHistory: () => request<Snapshot[]>("/api/portfolio/history"),
  getTrades: () => request<Trade[]>("/api/portfolio/trades"),

  getChatHistory: () => request<ChatMessage[]>("/api/chat/history"),
  chat: (message: string) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  getHealth: () => request<Health>("/api/health"),

  reset: () => request<Portfolio>("/api/reset", { method: "POST" }),
};
