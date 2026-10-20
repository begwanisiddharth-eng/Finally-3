"use client";

import LineChart from "./LineChart";
import Panel from "./Panel";
import { formatNumber, formatPercent, pnlClass } from "@/lib/format";
import { usePrices } from "@/providers/PricesProvider";

/** Large live-since-load chart for the selected ticker (section 10). */
export default function MainChart({ ticker }: { ticker: string | null }) {
  const { getBuffer, frame, prices } = usePrices();
  const live = ticker ? prices[ticker] : undefined;

  const title = ticker ? `Chart · ${ticker}` : "Chart";
  const price = live ? formatNumber(live.price) : "—";
  const pct = live ? formatPercent(live.day_change_percent) : "";

  return (
    <Panel
      title={title}
      action={
        ticker && (
          <span className="font-mono text-sm">
            <span className="tabular-nums">{price}</span>{" "}
            <span className={pnlClass(live?.day_change)}>{pct}</span>
          </span>
        )
      }
      className="h-full"
    >
      {ticker ? (
        <div className="h-full min-h-[240px] p-2">
          <LineChart
            key={ticker}
            data={getBuffer(ticker)}
            revision={frame}
            height={300}
            fill
            area
            color="#209dd7"
          />
        </div>
      ) : (
        <div className="flex h-full min-h-[240px] items-center justify-center text-sm text-fg-muted">
          Select a ticker from the watchlist.
        </div>
      )}
    </Panel>
  );
}
