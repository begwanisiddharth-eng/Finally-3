"use client";

import { useEffect, useRef, useState } from "react";
import type { Direction } from "@/lib/types";

/**
 * Returns a flash CSS class for ~250ms after the price actually moves.
 * Flashes only on a real tick-over-tick move (`direction != "flat"`), never
 * on a repeated unchanged frame (section 6, section 10).
 */
export function useFlash(price: number | null, direction: Direction | null): string {
  const prev = useRef<number | null>(price);
  const [cls, setCls] = useState("");

  useEffect(() => {
    const moved =
      prev.current != null &&
      price != null &&
      price !== prev.current &&
      direction != null &&
      direction !== "flat";
    prev.current = price;
    if (!moved) return;
    setCls(direction === "up" ? "flash-up" : "flash-down");
    const id = setTimeout(() => setCls(""), 260);
    return () => clearTimeout(id);
  }, [price, direction]);

  return cls;
}
