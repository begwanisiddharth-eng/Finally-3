import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import PositionsTable from "./PositionsTable";

const portfolio = {
  cash_balance: 985000,
  positions_value: 7500,
  total_value: 992500,
  unrealized_pnl: 250,
  positions: [
    {
      ticker: "HDFCBANK",
      quantity: 10,
      avg_cost: 725,
      current_price: 750,
      market_value: 7500,
      unrealized_pnl: 250,
      return_percent: 3.45,
    },
  ],
};

vi.mock("@/providers/AppDataProvider", () => ({
  useAppData: () => ({ portfolio }),
}));

describe("PositionsTable", () => {
  it("renders a position row with computed P&L and return", () => {
    render(<PositionsTable />);
    expect(screen.getByText("HDFCBANK")).toBeInTheDocument();
    expect(screen.getByText("725.00")).toBeInTheDocument();
    expect(screen.getByText("750.00")).toBeInTheDocument();
    expect(screen.getByText("+3.45%")).toBeInTheDocument();
  });
});
