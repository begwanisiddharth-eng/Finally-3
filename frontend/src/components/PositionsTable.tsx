"use client";

import Panel from "./Panel";
import { formatMoney, formatNumber, formatPercent, formatQty, pnlClass } from "@/lib/format";
import { useAppData } from "@/providers/AppDataProvider";

export default function PositionsTable() {
  const { portfolio } = useAppData();
  const positions = portfolio?.positions ?? [];

  return (
    <Panel title="Positions" className="h-full">
      {positions.length === 0 ? (
        <div className="p-3 text-sm text-fg-muted">No open positions.</div>
      ) : (
        <div className="max-h-[200px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-panel text-left text-[11px] uppercase text-fg-muted">
            <tr className="border-b border-border-soft">
              <th className="px-3 py-1.5 font-medium">Ticker</th>
              <th className="px-3 py-1.5 text-right font-medium">Qty</th>
              <th className="px-3 py-1.5 text-right font-medium">Avg Cost</th>
              <th className="px-3 py-1.5 text-right font-medium">Price</th>
              <th className="px-3 py-1.5 text-right font-medium">P&L</th>
              <th className="px-3 py-1.5 text-right font-medium">%</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.ticker} className="whitespace-nowrap border-b border-border-soft/60 font-mono tabular-nums">
                <td className="px-3 py-1.5 font-medium">{p.ticker}</td>
                <td className="px-3 py-1.5 text-right">{formatQty(p.quantity)}</td>
                <td className="px-3 py-1.5 text-right">{formatNumber(p.avg_cost)}</td>
                <td className="px-3 py-1.5 text-right">{formatNumber(p.current_price)}</td>
                <td className={`px-3 py-1.5 text-right ${pnlClass(p.unrealized_pnl)}`}>
                  {formatMoney(p.unrealized_pnl)}
                </td>
                <td className={`px-3 py-1.5 text-right ${pnlClass(p.return_percent)}`}>
                  {formatPercent(p.return_percent)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </Panel>
  );
}
