"use client";

import { useMemo } from "react";
import LineChart from "./LineChart";
import Panel from "./Panel";
import { useAppData } from "@/providers/AppDataProvider";
import type { LinePoint } from "@/providers/PricesProvider";

/** Total portfolio value over time, from portfolio_snapshots (section 10). */
export default function PnlChart() {
  const { history } = useAppData();

  // Last 60 minutes only (30s snapshots -> <=120 points), as a clean line.
  const data = useMemo<LinePoint[]>(() => {
    const points = history.map((s) => ({
      time: Math.floor(new Date(s.recorded_at).getTime() / 1000),
      value: s.total_value,
    }));
    if (points.length === 0) return points;
    const cutoff = points[points.length - 1].time - 3600;
    return points.filter((p) => p.time >= cutoff);
  }, [history]);

  return (
    <Panel title="Portfolio Value" className="h-full">
      <div className="h-full min-h-[160px] p-2">
        {data.length ? (
          <LineChart data={data} revision={data.length} height={200} color="#ecad0a" />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-fg-muted">
            No data yet.
          </div>
        )}
      </div>
    </Panel>
  );
}
