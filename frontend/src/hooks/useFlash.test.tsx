import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useFlash } from "./useFlash";

describe("useFlash", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("flashes up on an upward move", () => {
    const { result, rerender } = renderHook(({ p, d }) => useFlash(p, d), {
      initialProps: { p: 100, d: "up" as const },
    });
    expect(result.current).toBe("");
    rerender({ p: 101, d: "up" });
    expect(result.current).toBe("flash-up");
  });

  it("flashes down on a downward move", () => {
    const { result, rerender } = renderHook(({ p, d }) => useFlash(p, d), {
      initialProps: { p: 100, d: "down" as const },
    });
    rerender({ p: 99, d: "down" });
    expect(result.current).toBe("flash-down");
  });

  it("does not flash on an unchanged frame (same price / flat)", () => {
    const { result, rerender } = renderHook(({ p, d }) => useFlash(p, d), {
      initialProps: { p: 100, d: "flat" as const },
    });
    rerender({ p: 100, d: "flat" });
    expect(result.current).toBe("");
  });

  it("clears the class after the fade window", () => {
    const { result, rerender } = renderHook(({ p, d }) => useFlash(p, d), {
      initialProps: { p: 100, d: "up" as const },
    });
    rerender({ p: 101, d: "up" });
    expect(result.current).toBe("flash-up");
    act(() => vi.advanceTimersByTime(300));
    expect(result.current).toBe("");
  });
});
