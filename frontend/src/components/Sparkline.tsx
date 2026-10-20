"use client";

import LineChart from "./LineChart";
import { usePrices } from "@/providers/PricesProvider";

/** Mini live chart for a watchlist row, accumulated from the SSE stream. */
export default function Sparkline({ ticker, up }: { ticker: string; up: boolean }) {
  const { getBuffer, frame } = usePrices();
  const data = getBuffer(ticker);
  return (
    <div className="w-28">
      <LineChart
        data={data}
        revision={frame}
        height={32}
        minimal
        color={up ? "#26a66b" : "#e5484d"}
      />
    </div>
  );
}
