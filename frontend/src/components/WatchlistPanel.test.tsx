import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WatchlistPanel from "./WatchlistPanel";
import { api } from "@/lib/api";

const refreshWatchlist = vi.fn();

vi.mock("./Sparkline", () => ({ default: () => null }));

vi.mock("@/providers/AppDataProvider", () => ({
  useAppData: () => ({
    watchlist: [
      {
        ticker: "HDFCBANK",
        price: 750,
        previous_close: 740,
        day_change: 10,
        day_change_percent: 1.35,
        direction: "up",
        timestamp: 1,
      },
    ],
    refreshWatchlist,
  }),
}));

vi.mock("@/providers/PricesProvider", () => ({
  usePrices: () => ({ prices: {} }),
}));

vi.mock("@/lib/api", () => ({
  api: { addWatchlist: vi.fn(), removeWatchlist: vi.fn() },
  ApiError: class ApiError extends Error {},
}));

const mockApi = vi.mocked(api);

describe("WatchlistPanel", () => {
  beforeEach(() => {
    refreshWatchlist.mockClear();
    mockApi.addWatchlist.mockResolvedValue({ ticker: "WIPRO", added_at: "" });
    mockApi.removeWatchlist.mockResolvedValue({ ticker: "HDFCBANK", removed: true });
  });

  it("renders watchlist membership", () => {
    render(<WatchlistPanel selected={null} onSelect={() => {}} />);
    expect(screen.getByText("HDFCBANK")).toBeInTheDocument();
    expect(screen.getByText("750.00")).toBeInTheDocument();
    expect(screen.getByText("+1.35%")).toBeInTheDocument();
  });

  it("adds a ticker (normalized) and refreshes", async () => {
    const user = userEvent.setup();
    render(<WatchlistPanel selected={null} onSelect={() => {}} />);
    await user.type(screen.getByPlaceholderText("Add ticker…"), "wipro");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(mockApi.addWatchlist).toHaveBeenCalledWith("WIPRO");
    await waitFor(() => expect(refreshWatchlist).toHaveBeenCalled());
  });

  it("removes a ticker and refreshes", async () => {
    const user = userEvent.setup();
    render(<WatchlistPanel selected={null} onSelect={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Remove HDFCBANK" }));
    expect(mockApi.removeWatchlist).toHaveBeenCalledWith("HDFCBANK");
    await waitFor(() => expect(refreshWatchlist).toHaveBeenCalled());
  });

  it("selects a ticker on row click", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<WatchlistPanel selected={null} onSelect={onSelect} />);
    await user.click(screen.getByText("HDFCBANK"));
    expect(onSelect).toHaveBeenCalledWith("HDFCBANK");
  });
});
