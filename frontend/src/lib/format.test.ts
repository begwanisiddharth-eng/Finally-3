import { describe, it, expect } from "vitest";
import {
  formatMoney,
  formatNumber,
  formatPercent,
  formatQty,
  pnlClass,
} from "./format";

describe("format helpers", () => {
  it("formats rupees with Indian grouping", () => {
    expect(formatMoney(1000000)).toBe("Rs 10,00,000.00");
    expect(formatMoney(null)).toBe("—");
  });

  it("formats bare numbers to 2dp", () => {
    expect(formatNumber(750)).toBe("750.00");
    expect(formatNumber(null)).toBe("—");
  });

  it("signs percentages", () => {
    expect(formatPercent(1.35)).toBe("+1.35%");
    expect(formatPercent(-0.42)).toBe("-0.42%");
    expect(formatPercent(0)).toBe("0.00%");
  });

  it("trims trailing zeros on quantities", () => {
    expect(formatQty(10)).toBe("10");
    expect(formatQty(1.5)).toBe("1.5");
    expect(formatQty(0.25)).toBe("0.25");
  });

  it("maps sign to a color class", () => {
    expect(pnlClass(5)).toBe("text-up");
    expect(pnlClass(-5)).toBe("text-down");
    expect(pnlClass(0)).toBe("text-fg-muted");
    expect(pnlClass(null)).toBe("text-fg-muted");
  });
});
