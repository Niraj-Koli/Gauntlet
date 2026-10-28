"use client";

import { useQueries } from "@tanstack/react-query";
import Link from "next/link";

import { AllocationKey, AllocationStrip } from "@/components/charts/allocation-strip";
import { Swatch } from "@/components/ui/bits";
import { api, unwrap, type TraderSummary } from "@/lib/api";
import { traderColor } from "@/lib/colors";
import { keys } from "@/lib/keys";
import { useLive } from "@/lib/realtime";

/** Every trader's allocation, one strip each, so the floor's positioning reads at a glance. */
export function HoldingsBoard({ traders }: { traders: TraderSummary[] }) {
  const { mode } = useLive();
  const ids = traders.map((t) => t.id);
  const details = useQueries({
    queries: traders.map((t) => ({
      queryKey: keys.trader(t.slug),
      queryFn: () => unwrap(api.GET("/api/v1/traders/{slug}", { params: { path: { slug: t.slug } } })),
      refetchInterval: mode === "realtime" ? (false as const) : 10000,
    })),
  });
  return (
    <div className="flex flex-col gap-4 px-5 py-4">
      {traders.map((trader, i) => {
        const detail = details[i]?.data;
        return (
          <div key={trader.id} className="grid grid-cols-[7rem_1fr] items-center gap-3">
            <Link href={`/traders/${trader.slug}`} className="flex items-center gap-2 truncate text-sm font-medium hover:underline">
              <Swatch color={traderColor(trader.id, ids)} />
              {trader.name}
            </Link>
            {detail ? (
              <AllocationStrip holdings={detail.holdings} cash={detail.cash} total={detail.total_value} />
            ) : (
              <div className="h-[30px] rounded-[3px] bg-surface-2" />
            )}
          </div>
        );
      })}
      <AllocationKey />
    </div>
  );
}
