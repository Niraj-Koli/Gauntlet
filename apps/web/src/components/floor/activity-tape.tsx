"use client";

import Link from "next/link";

import { Empty, Swatch } from "@/components/ui/bits";
import type { Activity, TraderSummary } from "@/lib/api";
import { traderColor } from "@/lib/colors";
import { clock } from "@/lib/format";
import { cn } from "@/lib/utils";

import { describeActivity } from "./activity";

/** The floor's activity, newest first: trades, rejected orders, strategy rewrites, runs. */
export function ActivityTape({ activity, traders }: { activity: Activity[]; traders: TraderSummary[] }) {
  const ids = traders.map((t) => t.id);
  const idBySlug = new Map(traders.map((t) => [t.slug, t.id]));
  if (activity.length === 0) return <Empty>Nothing has happened yet. Runs and trades appear here as they happen.</Empty>;
  return (
    <ul className="divide-y divide-rule" aria-live="polite" aria-relevant="additions">
      {activity.map((item) => {
        const { text, tone } = describeActivity(item);
        const id = idBySlug.get(item.trader_slug);
        return (
          <li key={item.id} className="flex items-baseline gap-3 px-5 py-2.5 text-sm">
            <time dateTime={item.created_at} className="w-[5.5rem] shrink-0 text-xs text-muted tabular">
              {clock(item.created_at)}
            </time>
            <span className="min-w-0">
              <Link href={`/traders/${item.trader_slug}`} className="inline-flex items-baseline gap-1.5 font-medium hover:underline">
                {id != null ? <Swatch color={traderColor(id, ids)} className="translate-y-[1px]" /> : null}
                {item.trader_name}
              </Link>{" "}
              <span className={cn(tone === "reject" ? "text-loss" : tone === "run" ? "text-ink-2" : "text-ink")}>{text}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
