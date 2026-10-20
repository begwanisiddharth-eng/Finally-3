/** API response shapes — field names mirror the backend contract (PLAN.md section 8). */

export type Direction = "up" | "down" | "flat";

/** One ticker's entry in the SSE price map (PriceUpdate.to_dict, section 6). */
export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  previous_close: number;
  timestamp: number; // Unix seconds
  change: number;
  change_percent: number;
  day_change: number;
  day_change_percent: number;
  direction: Direction;
}

/** The SSE frame is a map of ticker -> PriceUpdate. */
export type PriceMap = Record<string, PriceUpdate>;

/** A row from GET /api/watchlist (price fields are null until the first tick). */
export interface WatchlistItem {
  ticker: string;
  price: number | null;
  previous_close: number | null;
  day_change: number | null;
  day_change_percent: number | null;
  direction: Direction | null;
  timestamp: number | null;
}

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number | null;
  market_value: number;
  unrealized_pnl: number;
  return_percent: number;
}

export interface Portfolio {
  cash_balance: number;
  positions_value: number;
  total_value: number;
  unrealized_pnl: number;
  positions: Position[];
}

export interface Trade {
  id: string;
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  executed_at: string;
}

export interface Snapshot {
  total_value: number;
  recorded_at: string;
}

export interface ChatAction {
  type: "trade" | "watchlist";
  ticker: string;
  status: "executed" | "failed";
  error: string | null;
  side?: "buy" | "sell";
  quantity?: number;
  price?: number;
  action?: "add" | "remove";
}

export interface ChatResponse {
  message: string;
  actions: ChatAction[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  actions: ChatAction[] | null;
  created_at: string;
}

export interface Health {
  status: string;
  data_source: "simulator" | "tapetide" | "none";
  market_data_healthy: boolean;
}
