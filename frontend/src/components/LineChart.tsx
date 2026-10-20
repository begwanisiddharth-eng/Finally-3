"use client";

import { useEffect, useRef } from "react";
import type {
  IChartApi,
  ISeriesApi,
  UTCTimestamp,
} from "lightweight-charts";
import type { LinePoint } from "@/providers/PricesProvider";

interface LineChartProps {
  /** Ascending, 1-per-second points. Read fresh on each `revision` change. */
  data: LinePoint[];
  /** Bumps whenever `data` has new content (buffer is mutated in place). */
  revision: number;
  height: number;
  color?: string;
  area?: boolean;
  /** Minimal chrome for sparklines (no axes, no grid, no crosshair). */
  minimal?: boolean;
  /** Fill the parent's height (which must be definite) instead of a fixed px
   * height, so the time axis is never clipped by a shorter container. */
  fill?: boolean;
}

/** Format a chart time (Unix seconds) as IST HH:MM for axis ticks and the crosshair.
 * Lightweight Charts renders times in UTC by default; this shows them in IST. */
function formatIST(time: unknown): string {
  const seconds = typeof time === "number" ? time : 0;
  return new Date(seconds * 1000).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  });
}

/** Coerce to strictly-ascending, unique-time data (last value wins per second). */
function toSeriesData(points: LinePoint[]) {
  const byTime = new Map<number, number>();
  for (const p of points) byTime.set(p.time, p.value);
  return [...byTime.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([time, value]) => ({ time: time as UTCTimestamp, value }));
}

export default function LineChart({
  data,
  revision,
  height,
  color = "#209dd7",
  area = false,
  minimal = false,
  fill = false,
}: LineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line" | "Area"> | null>(null);
  const dataRef = useRef(data);

  // Keep the latest data reachable from the create/sync effects.
  useEffect(() => {
    dataRef.current = data;
  });

  useEffect(() => {
    let disposed = false;
    const container = containerRef.current;
    if (!container) return;

    (async () => {
      const lwc = await import("lightweight-charts");
      if (disposed || !containerRef.current) return;

      const chart = lwc.createChart(containerRef.current, {
        autoSize: true,
        layout: {
          background: { type: lwc.ColorType.Solid, color: "transparent" },
          textColor: "#8b949e",
          attributionLogo: false,
          fontSize: 11,
        },
        localization: { timeFormatter: formatIST },
        grid: {
          vertLines: { visible: !minimal, color: "#21262d" },
          horzLines: { visible: !minimal, color: "#21262d" },
        },
        rightPriceScale: { visible: !minimal, borderColor: "#2a2f3a" },
        timeScale: {
          visible: !minimal,
          borderColor: "#2a2f3a",
          timeVisible: true,
          secondsVisible: false,
          tickMarkFormatter: formatIST,
        },
        crosshair: { mode: minimal ? 0 : 1 },
        handleScroll: !minimal,
        handleScale: !minimal,
      });

      const series = area
        ? chart.addSeries(lwc.AreaSeries, {
            lineColor: color,
            topColor: `${color}55`,
            bottomColor: `${color}08`,
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: !minimal,
          })
        : chart.addSeries(lwc.LineSeries, {
            color,
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: !minimal,
          });

      chartRef.current = chart;
      seriesRef.current = series;

      const initial = toSeriesData(dataRef.current);
      if (initial.length) {
        series.setData(initial);
        chart.timeScale().fitContent();
      }
    })();

    return () => {
      disposed = true;
      chartRef.current?.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
    // Recreate only when chart-shape options change.
  }, [area, minimal, color]);

  // Sync data on each revision bump.
  useEffect(() => {
    const series = seriesRef.current;
    const chart = chartRef.current;
    if (!series || !chart) return;
    const next = toSeriesData(dataRef.current);
    if (!next.length) return;
    series.setData(next);
    chart.timeScale().fitContent();
  }, [revision]);

  return (
    <div
      ref={containerRef}
      style={fill ? undefined : { height }}
      className={fill ? "h-full w-full" : "w-full"}
    />
  );
}
