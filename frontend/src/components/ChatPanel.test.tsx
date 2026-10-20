import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChatPanel from "./ChatPanel";
import { api } from "@/lib/api";
import type { ChatResponse } from "@/lib/types";

const refreshAfterTrade = vi.fn();

vi.mock("@/providers/AppDataProvider", () => ({
  useAppData: () => ({ refreshAfterTrade }),
}));

vi.mock("@/lib/api", () => ({
  api: { getChatHistory: vi.fn(), chat: vi.fn() },
  ApiError: class ApiError extends Error {},
}));

const mockApi = vi.mocked(api);

describe("ChatPanel", () => {
  beforeEach(() => {
    refreshAfterTrade.mockClear();
    mockApi.getChatHistory.mockResolvedValue([
      { role: "user", content: "hello there", actions: null, created_at: "" },
      { role: "assistant", content: "hi from finally", actions: [], created_at: "" },
    ]);
  });

  it("loads and renders prior history on mount", async () => {
    render(<ChatPanel />);
    expect(await screen.findByText("hello there")).toBeInTheDocument();
    expect(screen.getByText("hi from finally")).toBeInTheDocument();
  });

  it("shows a loading indicator and refetches when actions run", async () => {
    let resolveChat!: (r: ChatResponse) => void;
    mockApi.chat.mockReturnValue(new Promise((r) => (resolveChat = r)));
    const user = userEvent.setup();

    render(<ChatPanel />);
    await screen.findByText("hello there");

    const input = screen.getByPlaceholderText("Message FinAlly…");
    await user.type(input, "buy 1 HDFCBANK");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(screen.getByText("Thinking…")).toBeInTheDocument();
    expect(input).toBeDisabled();

    resolveChat({
      message: "Bought 1 HDFCBANK.",
      actions: [
        { type: "trade", ticker: "HDFCBANK", side: "buy", quantity: 1, status: "executed", error: null },
      ],
    });

    expect(await screen.findByText("Bought 1 HDFCBANK.")).toBeInTheDocument();
    await waitFor(() => expect(refreshAfterTrade).toHaveBeenCalled());
  });
});
