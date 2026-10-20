"use client";

import { useEffect, useState } from "react";
import ChatPanel from "@/components/ChatPanel";
import Header from "@/components/Header";
import Heatmap from "@/components/Heatmap";
import MainChart from "@/components/MainChart";
import PnlChart from "@/components/PnlChart";
import PositionsTable from "@/components/PositionsTable";
import RecentTrades from "@/components/RecentTrades";
import TradeBar from "@/components/TradeBar";
import WatchlistPanel from "@/components/WatchlistPanel";
import { AppDataProvider, useAppData } from "@/providers/AppDataProvider";
import { PricesProvider } from "@/providers/PricesProvider";

export default function Home() {
  return (
    <PricesProvider>
      <AppDataProvider>
        <Dashboard />
      </AppDataProvider>
    </PricesProvider>
  );
}

function Dashboard() {
  const { watchlist } = useAppData();
  const [selected, setSelected] = useState<string | null>(null);

  // Keep the chart on a watchlist ticker: auto-select the first one on load,
  // and when the selected ticker is removed from the watchlist, fall back to
  // the first remaining one (or nothing if the list is now empty). A selection
  // that is still on the watchlist is never overridden.
  useEffect(() => {
    const stillWatched = watchlist.some((w) => w.ticker === selected);
    if (!stillWatched) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelected(watchlist.length > 0 ? watchlist[0].ticker : null);
    }
  }, [selected, watchlist]);

  return (
    <div className="flex h-full flex-col">
      <Header />
      <div className="shrink-0 px-3 pt-3">
        <TradeBar selected={selected} />
      </div>

      <main className="min-h-0 flex-1 overflow-hidden p-3">
        <div className="grid h-full gap-3 lg:grid-cols-[320px_1fr_360px]">
          <div className="min-h-0 overflow-hidden lg:h-full">
            <WatchlistPanel selected={selected} onSelect={setSelected} />
          </div>

          <div className="flex min-h-0 flex-col gap-3 overflow-auto lg:h-full">
            <MainChart ticker={selected} />
            <div className="grid shrink-0 gap-3 md:grid-cols-2">
              <PnlChart />
              <Heatmap />
            </div>
            <div className="grid shrink-0 gap-3 md:grid-cols-2">
              <PositionsTable />
              <RecentTrades />
            </div>
          </div>

          <div className="min-h-0 overflow-hidden lg:h-full">
            <ChatPanel />
          </div>
        </div>
      </main>
    </div>
  );
}
