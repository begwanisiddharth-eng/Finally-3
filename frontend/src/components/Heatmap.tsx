"use client";

import Panel from "./Panel";
import { formatPercent } from "@/lib/format";
import { useAppData } from "@/providers/AppDataProvider";
import type { Position } from "@/lib/types";

/** Tint a position cell green (profit) / red (loss), intensity by |return %|. */
function tint(returnPercent: number): string {
  const alpha = Math.min(0.15 + Math.abs(returnPercent) / 20, 0.85);
  const base = returnPercent >= 0 ? "38, 166, 107" : "229, 72, 77";
  return `rgba(${base}, ${alpha.toFixed(2)})`;
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}
interface Tile {
  position: Position;
  weight: number;
  rect: Rect;
}

/** Worst aspect ratio of a row laid along `length` (Bruls et al.). */
function worst(areas: number[], length: number): number {
  const sum = areas.reduce((a, b) => a + b, 0);
  const max = Math.max(...areas);
  const min = Math.min(...areas);
  const s2 = sum * sum;
  const l2 = length * length;
  return Math.max((l2 * max) / s2, s2 / (l2 * min));
}

/** Squarified treemap: tile `positions` to fill the unit rect (0..100). */
function squarify(positions: Position[], total: number): Tile[] {
  const area = 100 * 100;
  const items = positions
    .map((p) => ({ position: p, value: (p.market_value / total) * area }))
    .sort((a, b) => b.value - a.value);

  const tiles: Tile[] = [];
  let rect: Rect = { x: 0, y: 0, w: 100, h: 100 };
  let row: typeof items = [];
  const queue = [...items];

  const layoutRow = () => {
    const sum = row.reduce((s, r) => s + r.value, 0);
    if (rect.w <= rect.h) {
      const rowH = sum / rect.w;
      let cx = rect.x;
      for (const r of row) {
        const rw = r.value / rowH;
        tiles.push({ position: r.position, weight: r.value / area, rect: { x: cx, y: rect.y, w: rw, h: rowH } });
        cx += rw;
      }
      rect = { x: rect.x, y: rect.y + rowH, w: rect.w, h: rect.h - rowH };
    } else {
      const rowW = sum / rect.h;
      let cy = rect.y;
      for (const r of row) {
        const rh = r.value / rowW;
        tiles.push({ position: r.position, weight: r.value / area, rect: { x: rect.x, y: cy, w: rowW, h: rh } });
        cy += rh;
      }
      rect = { x: rect.x + rowW, y: rect.y, w: rect.w - rowW, h: rect.h };
    }
  };

  while (queue.length) {
    const next = queue[0];
    const length = Math.min(rect.w, rect.h);
    const areas = row.map((r) => r.value);
    const curWorst = row.length ? worst(areas, length) : Infinity;
    const newWorst = worst([...areas, next.value], length);
    if (row.length === 0 || newWorst <= curWorst) {
      row.push(next);
      queue.shift();
    } else {
      layoutRow();
      row = [];
    }
  }
  if (row.length) layoutRow();
  return tiles;
}

/** Positions sized by weight (positions-only denominator), colored by P&L. */
export default function Heatmap() {
  const { portfolio } = useAppData();
  const positions = portfolio?.positions ?? [];
  const total = positions.reduce((sum, p) => sum + p.market_value, 0);

  return (
    <Panel title="Portfolio Heatmap" className="h-full">
      {positions.length === 0 || total === 0 ? (
        <div className="flex h-full min-h-[140px] items-center justify-center text-sm text-fg-muted">
          No positions yet.
        </div>
      ) : (
        <div className="relative h-full min-h-[160px] p-1">
          <div className="relative h-full w-full">
            {squarify(positions, total).map((t) => (
              <HeatCell key={t.position.ticker} tile={t} />
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}

function HeatCell({ tile }: { tile: Tile }) {
  const { position, rect, weight } = tile;
  return (
    <div
      className="absolute flex flex-col items-center justify-center overflow-hidden rounded p-1 text-center"
      style={{
        left: `${rect.x}%`,
        top: `${rect.y}%`,
        width: `${rect.w}%`,
        height: `${rect.h}%`,
        background: tint(position.return_percent),
        outline: "1px solid rgba(13, 17, 23, 0.6)",
      }}
      title={`${position.ticker} · ${(weight * 100).toFixed(1)}% of positions`}
    >
      <div className="truncate font-mono text-sm font-semibold">{position.ticker}</div>
      <div className="font-mono text-xs tabular-nums">{formatPercent(position.return_percent)}</div>
    </div>
  );
}
